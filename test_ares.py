from db import (
    init_db, evaluate_system_status, apply_protocol_effects,
    hash_pin, verify_pin, calculate_eva_readiness_detailed,
    record_auth_result, check_rate_limit
)
from theme import esc

def test_evaluate_system_status_thresholds():
    nominal_astro = {"hr": 65, "sys_bp": 115, "sleep": 7.5, "bone_t": -0.3, "muscle_idx": 95.0, "radiation_msv": 15.0, "stress_score": 2}
    res = evaluate_system_status(nominal_astro, "Earth Orbit (LEO Station)")
    assert all(v == "NOMINAL" for v in res.values())

def test_transition_clearance_does_not_mutate_vitals():
    baseline = {"hr": 82, "sys_bp": 128, "dia_bp": 80, "sleep": 6.5, "bone_t": -1.1, "muscle_idx": 88.0, "radiation_msv": 40.0}
    after = apply_protocol_effects(baseline, "TRANSITION_CLEARANCE")
    assert after == baseline

def test_eva_readiness_contributing_factors():
    astro = {"hr": 105, "sys_bp": 140, "sleep": 4.5, "bone_t": -2.0, "muscle_idx": 80.0, "radiation_msv": 130.0}
    state, prob, factors = calculate_eva_readiness_detailed(astro, "Deep Space Transit")
    assert state == "EVA RESTRICTED"
    assert prob < 75
    assert len(factors) == 5

def test_html_escaping_prevents_xss():
    malicious = "<script>alert('xss')</script>"
    escaped = esc(malicious)
    assert "<script>" not in escaped
    assert "&lt;script&gt;" in escaped

def test_auth_rate_limiting_locks_after_five_failures():
    init_db()
    target = "TEST-LOCK-USER"
    record_auth_result(target, True)  # Reset state
    for _ in range(5):
        allowed, _ = record_auth_result(target, False)
    is_allowed, wait_sec = check_rate_limit(target)
    assert is_allowed is False
    assert wait_sec > 0
    record_auth_result(target, True)  # Clean up
