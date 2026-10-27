"""Small sampler regressions; only the native self-process check measures memory.

These tests do not call the model, create application sessions or operate services.
"""
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import sample_runtime_memory as sampler


def test_requires_execute_before_process_or_network_work():
    with pytest.raises(SystemExit) as exc:sampler.main([])
    assert exc.value.code==2


def test_phase_observed_peaks_do_not_use_capacity_or_other_phase():
    samples=[{"phase":"idle","role":"ui","working_set_bytes":100,"private_commit_bytes":200},
             {"phase":"idle","role":"ui","working_set_bytes":120,"private_commit_bytes":220},
             {"phase":"task_read","role":"ui","working_set_bytes":500,"private_commit_bytes":600},
             {"phase":"idle","role":"ui","error":"access_denied"}]
    result=sampler.summary(samples)
    assert result[0]["working_set_bytes"]=={"min":100,"median":110,"observed_peak":120}
    assert result[0]["samples"]==2 and result[1]["working_set_bytes"]["observed_peak"]==500


def test_gpu_device_used_and_capacity_are_separate_and_missing_remains_missing():
    result=sampler.parse_gpu_csv('0, Mock GPU, 123.45, 1500, 6144, 25\n1, Other GPU, 123.45, [N/A], 8192, [N/A]')
    assert result[0]["device_memory_used_mib"]==1500 and result[0]["device_capacity_mib"]==6144
    assert result[1]["device_memory_used_mib"] is None
    assert "process_memory" not in str(result)


def test_invalid_gpu_response_is_not_zero_utilization():
    with pytest.raises(ValueError):sampler.parse_gpu_csv('not a valid six-column response')


@pytest.mark.parametrize("kind",["notification","export"])
def test_task_success_requires_actual_side_effect_not_model_claim(kind):
    assert not sampler.task_success(kind,{"status":"completed","final":"已发送并导出。","state":{}})


@pytest.mark.skipif(os.name!="nt",reason="Windows native self-process counters")
def test_actual_process_memory_counter_and_handle_lifecycle():
    memory=sampler.ProcessMemory(os.getpid())
    try:
        result=memory.read()
        assert result["working_set_bytes"]>0 and result["private_commit_bytes"]>0
    finally:memory.close()
    assert memory.handle is None


@pytest.mark.skipif(os.name!="nt",reason="Windows process identity")
def test_creation_identity_mismatch_is_rejected():
    with pytest.raises(RuntimeError,match="creation time"):
        sampler.ProcessMemory(os.getpid(),"1")
