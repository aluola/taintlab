"""Upload parsing regressions using synthetic files and disposable local workers."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import zipfile

import pytest

from taintlab.web import uploads


def make_docx(document=None, extra=(), compression=zipfile.ZIP_STORED):
    if document is None:
        document = f'<w:document xmlns:w="{uploads.WORD_NAMESPACE}"><w:body><w:p><w:r><w:t>项目会议周三召开</w:t></w:r><w:r><w:instrText>DO_NOT_EXTRACT_FIELD</w:instrText></w:r></w:p><w:p><w:r><w:t>合法摘要</w:t></w:r></w:p></w:body></w:document>'.encode()
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr("word/document.xml", document)
        for name, content in extra:
            archive.writestr(name, content)
    return stream.getvalue()


def make_pdf(text="Meeting Wednesday 15:00", pages=1, action=None, encrypted=False, bomb=False):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, TextStringObject
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=300, height=200)
        if text:
            font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
            stream = DecodedStreamObject()
            stream.set_data(b"BT /F1 12 Tf 10 100 Td (" + text.encode("ascii") + b") Tj ET" + (b" " * (uploads.MAX_EXPANDED_BYTES + 1) if bomb else b""))
            page[NameObject("/Contents")] = writer._add_object(stream.flate_encode() if bomb else stream)
    if action == "javascript":
        writer._root_object[NameObject("/OpenAction")] = DictionaryObject({NameObject("/S"): NameObject("/JavaScript"), NameObject("/JS"): TextStringObject("app.alert('must not execute')")})
    elif action == "attachment":
        writer.add_attachment("payload.txt", b"not extracted")
    elif action == "link":
        writer._root_object[NameObject("/SyntheticLink")] = DictionaryObject({NameObject("/S"): NameObject("/URI"), NameObject("/URI"): TextStringObject("https://example.invalid/never-request")})
    if encrypted:
        writer.encrypt("test-password")
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


def assert_error(call, code):
    with pytest.raises(uploads.UploadError) as raised:
        call()
    assert raised.value.code == code
    assert raised.value.message == uploads.ERROR_MESSAGES[code]
    assert str(raised.value) == uploads.ERROR_MESSAGES[code]


@pytest.mark.parametrize("extension", ["txt", "MD"])
def test_real_worker_accepts_utf8_bom_and_preserves_untrusted_instruction_text(extension):
    raw = b"\xef\xbb\xbf" + "提示注入教材讨论：忽略指令只是引用；会议周三下午三点。".encode()
    result = uploads.parse_upload("教材." + extension, raw)
    assert result == {"text": raw.decode("utf-8-sig"), "warnings": [], "characters": len(raw.decode("utf-8-sig")),
                      "format": extension.lower(), "content_hash": hashlib.sha256(raw).hexdigest()}


def test_real_docx_worker_extracts_only_word_text_and_paragraph_boundaries():
    result = uploads.parse_upload("会议.docx", make_docx())
    assert result["text"] == "项目会议周三召开\n合法摘要"
    assert "DO_NOT_EXTRACT_FIELD" not in result["text"]
    assert result["format"] == "docx" and result["characters"] == len(result["text"])


def test_real_pdf_worker_extracts_text_without_running_an_application():
    result = uploads.parse_upload("meeting.pdf", make_pdf())
    assert "Meeting Wednesday 15:00" in result["text"] and result["warnings"] == []


def test_real_worker_rejects_invalid_utf8_with_static_content_free_error():
    raw = b"PRIVATE_UPLOADED_CONTENT\xff"
    assert_error(lambda: uploads.parse_upload("private.txt", raw), "invalid_utf8")


@pytest.mark.parametrize("name,content,code", [
    ("bad.exe", b"hello", "unsupported_format"),
    ("bad.txt", b"", "empty_file"),
    ("bad.txt", "oversize_fixture", "file_too_large"),
    ("bad.txt", "not-bytes", "invalid_upload"),
    ("a\x00.txt", b"hello", "invalid_upload"),
], ids=["unsupported", "empty", "oversize", "not_bytes", "invalid_name"])
def test_initial_limits_fail_before_creating_any_worker(monkeypatch, name, content, code):
    monkeypatch.setattr(uploads.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Unexpected worker"))
    if code == "file_too_large":
        content = b"x" * (uploads.MAX_FILE_BYTES + 1)
    assert_error(lambda: uploads.parse_upload(name, content), code)


def test_text_truncation_has_exact_returned_character_count_and_original_hash():
    content = ("界" * 10001).encode()
    result = uploads.parse_upload("large.md", content)
    assert len(result["text"]) == result["characters"] == 10000
    assert result["warnings"] == [uploads.TRUNCATED_WARNING]
    assert result["content_hash"] == hashlib.sha256(content).hexdigest()


@pytest.mark.parametrize("name", ["../../escape.xml", "/absolute.xml", "C:/escape.xml", "word\\escape.xml", "word//escape.xml", "word/./escape.xml"])
def test_docx_paths_are_rejected_without_host_extraction(name):
    normalized = name.replace("\\", "/")
    archive = make_docx(extra=[(normalized, b"payload")])
    if "\\" in name:
        archive = archive.replace(normalized.encode(), name.encode())
    assert_error(lambda: uploads._parse_content("docx", archive), "unsafe_archive")


def test_docx_duplicate_case_and_symlink_entries_are_rejected():
    assert_error(lambda: uploads._parse_content("docx", make_docx(extra=[("WORD/document.XML", b"duplicate")])), "unsafe_archive")
    link = zipfile.ZipInfo("word/link.xml")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    assert_error(lambda: uploads._parse_content("docx", make_docx(extra=[(link, b"../../target")])), "unsafe_archive")


@pytest.mark.parametrize("limit", ["entries", "expanded", "ratio"])
def test_docx_compression_limits_are_enforced_before_xml_parsing(limit):
    if limit == "entries":
        value = make_docx(extra=[(f"word/unused{i}.txt", b"x") for i in range(127)])
    elif limit == "expanded":
        value = make_docx(extra=[("word/data.txt", b"x" * (uploads.MAX_EXPANDED_BYTES + 1))], compression=zipfile.ZIP_DEFLATED)
    else:
        value = make_docx(extra=[("word/data.txt", b"x" * 100000)], compression=zipfile.ZIP_DEFLATED)
    assert_error(lambda: uploads._parse_content("docx", value), "archive_limit")


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_docx_doctype_entities_rejected_in_supported_xml_encodings(encoding):
    xml = f'<?xml version="1.0" encoding="{encoding}"?><!DOCTYPE document [<!ENTITY leak SYSTEM "file:///never-read.txt">]><w:document xmlns:w="{uploads.WORD_NAMESPACE}"><w:body><w:p><w:r><w:t>&leak;</w:t></w:r></w:p></w:body></w:document>'
    assert_error(lambda: uploads._parse_content("docx", make_docx(document=xml.encode(encoding))), "unsafe_xml")


def test_docx_entity_declarations_in_auxiliary_xml_are_also_rejected():
    assert_error(lambda: uploads._parse_content("docx", make_docx(extra=[("word/comments.XML", b'<!DOCTYPE comments [<!ENTITY a "x">]><comments/>')])), "unsafe_xml")


@pytest.mark.parametrize("entry", ["word/vbaProject.bin", "word/embeddings/payload.bin", "word/activeX/control.bin", "word/macro.js"])
def test_docx_embedded_or_active_payloads_are_rejected(entry):
    assert_error(lambda: uploads._parse_content("docx", make_docx(extra=[(entry, b"never executed")])), "active_content")


def test_docx_external_links_are_not_resolved_and_only_static_warning_is_returned():
    relations = b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" TargetMode="External" Target="https://example.invalid/private"/></Relationships>'
    result = uploads.parse_upload("linked.docx", make_docx(extra=[("word/_rels/document.xml.rels", relations)]))
    assert result["warnings"] == [uploads.EXTERNAL_WARNING]
    assert "example.invalid" not in result["text"]


@pytest.mark.parametrize("variant,code", [("empty", "pdf_no_text"), ("pages", "pdf_page_limit"), ("encrypted", "protected_document"), ("javascript", "active_content"), ("attachment", "active_content"), ("bomb", "resource_limit")])
def test_pdf_rejects_no_text_excessive_pages_encryption_active_content_and_stream_bombs(variant, code):
    content = make_pdf(text="" if variant == "empty" else "Valid text", pages=51 if variant == "pages" else 1,
                       encrypted=variant == "encrypted", action=variant, bomb=variant == "bomb")
    assert_error(lambda: uploads._parse_content("pdf", content), code)


def test_pdf_plain_hyperlink_is_ignored_without_losing_legitimate_text():
    result = uploads.parse_upload("linked.pdf", make_pdf(action="link"))
    assert result["warnings"] == [uploads.EXTERNAL_WARNING]
    assert "Meeting Wednesday" in result["text"]


def test_worker_disables_socket_dns_and_subprocess_execution_in_its_own_process():
    path = str(Path(uploads.__file__).resolve())
    code = ("import runpy,socket,subprocess,json\n"
            f"m=runpy.run_path({path!r},run_name='upload_guard_test')\n"
            "m['_deny_capabilities']()\n"
            "checks=[]\n"
            "for call in [lambda: socket.create_connection(('127.0.0.1',1)),lambda: socket.getaddrinfo('example.invalid',80),lambda: socket.socket().sendto(b'x',('127.0.0.1',1)),lambda: subprocess.Popen(['never-run'])]:\n"
            " try: call()\n"
            " except PermissionError: checks.append(True)\n"
            " else: checks.append(False)\n"
            "print(json.dumps(checks))\n")
    result = subprocess.run([sys._base_executable, "-I", "-c", code], capture_output=True, text=True, timeout=8)
    assert result.returncode == 0 and json.loads(result.stdout) == [True, True, True, True]


def test_untrusted_filename_never_reaches_host_paths_and_temporary_data_is_cleaned(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setenv("UPLOAD_TEST_PRIVATE_ENV", "never-pass-to-worker")
    actual_popen = subprocess.Popen
    def popen(*args, **kwargs):
        assert "UPLOAD_TEST_PRIVATE_ENV" not in kwargs["env"]
        assert set(kwargs["env"]) <= {"SystemRoot", "WINDIR", "TEMP", "TMP"}
        assert Path(kwargs["cwd"]).parent == tmp_path
        return actual_popen(*args, **kwargs)
    monkeypatch.setattr(uploads.subprocess, "Popen", popen)
    commands = []
    original = uploads._worker_command
    def command(kind, source, result):
        assert source.parent == result.parent and source.parent.parent == tmp_path
        assert source.parent.name.startswith("taintlab-upload-")
        assert source.name == "content.bin" and result.name == "result.json"
        value = original(kind, source, result)
        commands.append(value)
        assert value[0] == str(Path(sys._base_executable).resolve()) and value[1] == "-I"
        return value
    monkeypatch.setattr(uploads, "_worker_command", command)
    result = uploads.parse_upload("../../never-create-this-name.txt", b"safe local text")
    assert result["text"] == "safe local text"
    assert all("never-create-this-name" not in part for part in commands[0])
    assert list(tmp_path.iterdir()) == []


def test_real_eight_second_timeout_terminates_actual_worker_and_cleans_temporary_files(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads.tempfile, "tempdir", str(tmp_path))
    actual_popen = subprocess.Popen
    processes = []
    def capture(*args, **kwargs):
        process = actual_popen(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(uploads.subprocess, "Popen", capture)
    monkeypatch.setattr(uploads, "_worker_command", lambda *args: [sys._base_executable, "-I", "-c", "import time; time.sleep(60)"])
    started = time.monotonic()
    assert uploads.WORKER_TIMEOUT_SECONDS == 8.0
    assert_error(lambda: uploads.parse_upload("wait.txt", b"synthetic timeout fixture"), "parse_timeout")
    elapsed = time.monotonic() - started
    assert 8 <= elapsed < 14
    assert len(processes) == 1 and processes[0].poll() is not None
    assert list(tmp_path.iterdir()) == []


def test_malformed_worker_result_cannot_inject_error_content(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads.tempfile, "tempdir", str(tmp_path))
    def command(kind, source, result):
        code = f"from pathlib import Path;Path({str(result)!r}).write_text('{{\"error\":\"UPLOADED_PRIVATE_CONTENT\"}}',encoding='utf-8')"
        return [sys._base_executable, "-I", "-c", code]
    monkeypatch.setattr(uploads, "_worker_command", command)
    assert_error(lambda: uploads.parse_upload("private.txt", b"private"), "parse_failed")
    assert list(tmp_path.iterdir()) == []
