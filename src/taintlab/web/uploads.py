"""Bounded, local text extraction for untrusted uploads; never an execution API.

The public function launches a disposable base-interpreter process. On Windows
this avoids the venv redirector, so timeout termination targets the actual worker.
Returned text is still untrusted content and must be registered by the caller.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import sysconfig
import tempfile
import uuid
import xml.etree.ElementTree as ET
import zipfile

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_EXPANDED_BYTES = 8 * 1024 * 1024
MAX_ZIP_ENTRIES = 128
MAX_COMPRESSION_RATIO = 100
MAX_TEXT_CHARACTERS = 10_000
MAX_PDF_PAGES = 50
WORKER_TIMEOUT_SECONDS = 8.0
MAX_RESULT_BYTES = 128 * 1024
FORMATS = {"txt", "md", "pdf", "docx"}
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
TRUNCATED_WARNING = "提取文本超过 10000 字符，已截断；未将剩余内容加入任务。"
EXTERNAL_WARNING = "已忽略文档中的外部链接，不会发起网络请求。"
ERROR_MESSAGES = {
    "invalid_upload": "上传参数无效，请选择本地文件后重试。",
    "unsupported_format": "仅支持 TXT、MD、文本型 PDF 和 DOCX 文件。",
    "file_too_large": "上传文件超过 2 MiB 大小限制。",
    "empty_file": "上传文件为空。",
    "invalid_utf8": "文本文件必须使用严格 UTF-8 编码，可包含 UTF-8 BOM。",
    "no_text": "文件中未找到可读取的文本。",
    "pdf_no_text": "PDF 中未找到文本层；扫描件需要先在本地完成 OCR。",
    "pdf_page_limit": "PDF 超过 50 页限制。",
    "protected_document": "不支持加密或受密码保护的文档。",
    "unsafe_archive": "DOCX 包含不安全、重复或越界的压缩条目。",
    "archive_limit": "DOCX 超过展开大小、条目数量或压缩比限制。",
    "unsafe_xml": "文档 XML 包含禁止的实体或文档类型声明。",
    "active_content": "文档包含不支持的宏、脚本、自动动作或嵌入对象。",
    "resource_limit": "文档解析超过资源限制。",
    "parse_timeout": "文档解析超过 8 秒，解析进程已终止。",
    "parser_dependency": "本地文档解析依赖未就绪，请重新安装项目锁定依赖。",
    "parse_failed": "无法解析此文件，请检查文件格式或重新导出为纯文本。",
}


class UploadError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _error(code: str) -> UploadError:
    code = code if code in ERROR_MESSAGES else "parse_failed"
    return UploadError(code, ERROR_MESSAGES[code])


def _finish(text: str, warnings: list[str], kind: str, content: bytes) -> dict:
    if not text.strip():
        raise _error("pdf_no_text" if kind == "pdf" else "no_text")
    if len(text) > MAX_TEXT_CHARACTERS:
        text = text[:MAX_TEXT_CHARACTERS]
        warnings.append(TRUNCATED_WARNING)
    return {"text": text, "warnings": list(dict.fromkeys(warnings)), "characters": len(text),
            "format": kind, "content_hash": hashlib.sha256(content).hexdigest()}


def _xml(raw: bytes):
    # Removing NUL bytes also recognizes declarations in UTF-16/UTF-32 XML.
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", raw.replace(b"\x00", b""), re.I):
        raise _error("unsafe_xml")
    return ET.fromstring(raw)


def _docx(content: bytes) -> tuple[str, list[str]]:
    warnings = []
    with zipfile.ZipFile(BytesIO(content)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ZIP_ENTRIES or sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES:
            raise _error("archive_limit")
        seen = set()
        for entry in entries:
            # ZipInfo normalizes backslashes on Windows; inspect the raw member
            # name as well so that this normalization cannot hide unsafe input.
            name = entry.orig_filename
            parts = name.rstrip("/").split("/")
            if (not name or len(name) > 512 or name.startswith("/") or "\\" in name or ":" in name or
                    any(part in {"", ".", ".."} for part in parts) or "\x00" in name or
                    name.casefold() in seen or stat.S_ISLNK(entry.external_attr >> 16)):
                raise _error("unsafe_archive")
            seen.add(name.casefold())
            if entry.flag_bits & 1:
                raise _error("protected_document")
            if entry.file_size > max(entry.compress_size, 1) * MAX_COMPRESSION_RATIO:
                raise _error("archive_limit")
            lowered = name.casefold()
            if ("vbaproject" in lowered or any(part.casefold() in {"embeddings", "activex"} for part in parts) or
                    Path(lowered).suffix in {".exe", ".dll", ".js", ".vbs", ".ps1", ".cmd", ".bat"}):
                raise _error("active_content")
        names = {entry.filename for entry in entries}
        if not {"[Content_Types].xml", "word/document.xml"} <= names:
            raise _error("parse_failed")
        document = None
        actual_total = 0
        for entry in entries:
            if entry.is_dir():
                continue
            # No extract/extractall: archive paths are never used on the host.
            with archive.open(entry) as stream:
                raw = stream.read(MAX_EXPANDED_BYTES + 1)
            actual_total += len(raw)
            if len(raw) != entry.file_size or actual_total > MAX_EXPANDED_BYTES:
                raise _error("archive_limit")
            if entry.filename.casefold().endswith((".xml", ".rels")):
                tree = _xml(raw)
                if entry.filename == "[Content_Types].xml" and any(
                        any(word in element.attrib.get("ContentType", "").casefold() for word in ("macroenabled", "vbaproject", "activex"))
                        for element in tree.iter()):
                    raise _error("active_content")
                if entry.filename.endswith(".rels") and any(
                        element.attrib.get("TargetMode", "").casefold() == "external" for element in tree.iter()):
                    warnings.append(EXTERNAL_WARNING)
                if entry.filename == "word/document.xml":
                    document = tree
        if document is None or document.tag != f"{{{WORD_NAMESPACE}}}document":
            raise _error("parse_failed")
        pieces = []
        # Only w:t contributes source text. Field instructions, properties,
        # comments and drawing metadata are not executed or extracted.
        def walk(element):
            if element.tag == f"{{{WORD_NAMESPACE}}}t":
                pieces.append(element.text or "")
            else:
                for child in element:
                    walk(child)
            if element.tag == f"{{{WORD_NAMESPACE}}}p":
                pieces.append("\n")
        walk(document)
        return "".join(pieces).rstrip("\n"), warnings


def _pdf(content: bytes) -> tuple[str, list[str]]:
    if not content.startswith(b"%PDF-"):
        raise _error("parse_failed")
    try:
        from pypdf import PdfReader, apply_configuration
        from pypdf.errors import LimitReachedError
        from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject
    except ImportError:
        raise _error("parser_dependency") from None
    warnings = []
    forbidden = {"/JavaScript", "/JS", "/Launch", "/OpenAction", "/AA", "/EmbeddedFiles", "/EmbeddedFile", "/RichMedia", "/XFA", "/SubmitForm", "/ImportData", "/GoToR", "/GoToE"}
    limits = {"maximum_declared_stream_length": MAX_EXPANDED_BYTES,
              "array_based_stream_maximum_output_length": MAX_EXPANDED_BYTES,
              "zlib_maximum_output_length": MAX_EXPANDED_BYTES,
              "lzw_maximum_output_length": MAX_EXPANDED_BYTES,
              "run_length_maximum_output_length": MAX_EXPANDED_BYTES,
              "brotli_maximum_output_length": MAX_EXPANDED_BYTES,
              "stream_decoding_work_maximum_length": 2 * MAX_EXPANDED_BYTES,
              "stream_filters_maximum_length": 4, "stream_parsing_work_maximum_count": 100_000,
              "array_maximum_element_count": 10_000, "dictionary_maximum_element_count": 10_000,
              "page_tree_maximum_entries": 256, "page_tree_maximum_depth": 30,
              "xform_maximum_invocations_per_extraction": 500, "jbig2dec_binary": None}
    try:
        with apply_configuration(**limits):
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise _error("protected_document")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise _error("pdf_page_limit")
            pending = [reader.trailer]
            seen_objects, seen_refs = set(), set()
            while pending:
                value = pending.pop()
                if isinstance(value, IndirectObject):
                    key = (value.idnum, value.generation)
                    if key in seen_refs:
                        continue
                    seen_refs.add(key)
                    value = value.get_object()
                if isinstance(value, (DictionaryObject, ArrayObject)):
                    if id(value) in seen_objects:
                        continue
                    seen_objects.add(id(value))
                    if len(seen_objects) + len(seen_refs) > 20_000:
                        raise _error("resource_limit")
                if isinstance(value, DictionaryObject):
                    if any(str(key) in forbidden for key in value) or any(str(value.get(key, "")) in forbidden for key in ("/S", "/Type", "/Subtype")):
                        raise _error("active_content")
                    if "/URI" in value:
                        warnings.append(EXTERNAL_WARNING)
                    pending.extend(value.values())
                elif isinstance(value, ArrayObject):
                    pending.extend(value)
            pieces, count = [], 0
            for page in reader.pages:
                text = page.extract_text() or ""
                pieces.append(text[:MAX_TEXT_CHARACTERS + 1])
                count += len(pieces[-1]) + (1 if len(pieces) > 1 else 0)
                if count > MAX_TEXT_CHARACTERS:
                    break
            return "\n".join(pieces), warnings
    except LimitReachedError:
        raise _error("resource_limit") from None


def _parse_content(kind: str, content: bytes) -> dict:
    try:
        if kind in {"txt", "md"}:
            try:
                text = content.decode("utf-8-sig", errors="strict")
            except UnicodeDecodeError:
                raise _error("invalid_utf8") from None
            warnings = []
        elif kind == "docx":
            text, warnings = _docx(content)
        elif kind == "pdf":
            text, warnings = _pdf(content)
        else:
            raise _error("unsupported_format")
        return _finish(text, warnings, kind, content)
    except UploadError:
        raise
    except (MemoryError, RecursionError):
        raise _error("resource_limit") from None
    except Exception:
        raise _error("parse_failed") from None


def _deny_capabilities():
    import socket
    def denied(*args, **kwargs):
        raise PermissionError("Upload worker capability disabled")
    for name in ("connect", "connect_ex", "sendto", "sendmsg", "sendall", "bind", "listen", "accept"):
        if hasattr(socket.socket, name):
            setattr(socket.socket, name, denied)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        setattr(socket, name, denied)
    subprocess.Popen = denied
    for name in ("system", "popen", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe"):
        if hasattr(os, name):
            setattr(os, name, denied)


def _worker_command(kind: str, source: Path, result: Path) -> list[str]:
    # Explicit trusted package directory replaces venv startup redirection. -I
    # ignores caller PYTHONPATH and user-site startup hooks.
    python = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
    purelib = Path(sysconfig.get_paths()["purelib"]).resolve()
    return [str(python), "-I", str(Path(__file__).resolve()), "--worker", kind, str(source), str(result), str(purelib)]


def parse_upload(filename: str, content: bytes) -> dict:
    """Return bounded untrusted text or raise a static, content-free UploadError.

    ``characters`` is the length of the returned (possibly truncated) text.
    The SHA256 is over the original bytes, including any UTF-8 BOM.
    """
    if not isinstance(filename, str) or not filename or len(filename) > 512 or "\x00" in filename or not isinstance(content, bytes):
        raise _error("invalid_upload")
    kind = filename.rpartition(".")[2].casefold()
    if kind not in FORMATS:
        raise _error("unsupported_format")
    if len(content) > MAX_FILE_BYTES:
        raise _error("file_too_large")
    if not content:
        raise _error("empty_file")
    # The user filename is never part of a host path or worker command.
    with tempfile.TemporaryDirectory(prefix="taintlab-upload-" + uuid.uuid4().hex + "-") as directory:
        source, result = Path(directory) / "content.bin", Path(directory) / "result.json"
        source.write_bytes(content)
        process = None
        try:
            process = subprocess.Popen(_worker_command(kind, source, result), stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                                       cwd=directory, env={name: os.environ[name] for name in ("SystemRoot", "WINDIR", "TEMP", "TMP") if name in os.environ},
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            try:
                process.wait(timeout=WORKER_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
                raise _error("parse_timeout") from None
            if process.returncode or not result.is_file() or result.stat().st_size > MAX_RESULT_BYTES:
                raise _error("parse_failed")
            payload = json.loads(result.read_text(encoding="utf-8"))
            if "error" in payload:
                raise _error(payload["error"])
            text, warnings = payload.get("text"), payload.get("warnings")
            if (not isinstance(text, str) or len(text) > MAX_TEXT_CHARACTERS or not isinstance(warnings, list) or
                    any(item not in {TRUNCATED_WARNING, EXTERNAL_WARNING} for item in warnings) or
                    payload.get("characters") != len(text) or payload.get("format") != kind or
                    payload.get("content_hash") != hashlib.sha256(content).hexdigest()):
                raise _error("parse_failed")
            return {key: payload[key] for key in ("text", "warnings", "characters", "format", "content_hash")}
        except UploadError:
            raise
        except Exception:
            raise _error("parse_failed") from None
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=2)


if __name__ == "__main__":
    # Worker arguments are made exclusively by _worker_command, not the UI.
    if len(sys.argv) != 6 or sys.argv[1] != "--worker" or sys.argv[2] not in FORMATS:
        raise SystemExit(2)
    _, _, kind, source, result, purelib = sys.argv
    sys.path.insert(0, purelib)
    logging.disable(logging.CRITICAL)
    _deny_capabilities()
    try:
        raw = Path(source).read_bytes()
        if not raw or len(raw) > MAX_FILE_BYTES:
            raise _error("invalid_upload")
        answer = _parse_content(kind, raw)
    except UploadError as error:
        answer = {"error": error.code}
    except Exception:
        answer = {"error": "parse_failed"}
    Path(result).write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
