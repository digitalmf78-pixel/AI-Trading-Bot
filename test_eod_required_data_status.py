import copy

from v8_layers_14_41 import _eod_required_data_status


def _ready_row():
    return {
        "CoreTechnicalScreenStatus": "PASS",
        "SectorStrengthStatus": "PASS",
        "MarketRegimeStatus": "PASS",
        "DeliveryStatus": "PASS",
        "AccumulationDistributionStatus": "PASS",
        "NewsStatus": "PASS",
        "RiskRewardStatus": "PASS",
        "RiskControlStatus": "PASS",
        "MandatoryConfirmationStatus": "PASS",
        "ChaseStatus": "CLEAR",
        "MarketRegime": "RISK_ON",
        "DeliveryFilterStatus": "PASS_GE_60_PERCENT",
        "AccumulationDistribution": "Accumulation",
        "SetupType": "Breakout",
        "V8ScoreCoveragePct": 100.0,
        "RVOL": 2.0,
        "V8Score": 82.0,
        "VolumeReason": "Demand-led",
    }


def test_complete_final_eod_inputs_are_ready():
    assert _eod_required_data_status(_ready_row()) == "READY"


def test_missing_mandatory_confirmation_is_wait_not_skip():
    row = _ready_row()
    row.pop("MandatoryConfirmationStatus")
    assert _eod_required_data_status(row) == "WAIT_FOR_DATA"


def test_missing_chase_status_is_wait_not_skip():
    row = _ready_row()
    row.pop("ChaseStatus")
    assert _eod_required_data_status(row) == "WAIT_FOR_DATA"


def test_missing_rvol_is_wait_not_synthetic_no_volume_reason():
    row = _ready_row()
    row.pop("RVOL")
    assert _eod_required_data_status(row) == "WAIT_FOR_DATA"


def test_missing_volume_reason_when_rvol_high_is_wait():
    row = _ready_row()
    row.pop("VolumeReason")
    assert _eod_required_data_status(row) == "WAIT_FOR_DATA"


def test_volume_reason_not_required_below_existing_rvol_threshold():
    row = _ready_row()
    row["RVOL"] = 1.2
    row.pop("VolumeReason")
    assert _eod_required_data_status(row) == "READY"


def test_core_technical_reject_remains_decisive():
    row = {}
    row["CoreTechnicalScreenStatus"] = "REJECT"
    assert _eod_required_data_status(row) == "REJECT"


def test_valid_supply_led_reason_is_a_failed_setup_not_missing_data():
    row = _ready_row()
    row["VolumeReason"] = "Supply-led"
    assert _eod_required_data_status(row) == "READY"
