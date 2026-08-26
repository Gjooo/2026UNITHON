"""Central MVP workload-estimation assumptions; none are measured values."""

VRAM_GB_PER_BILLION_PARAMETERS = {
    "full_finetuning": 16.0,
    "lora": 4.0,
    "qlora": 2.0,
    "inference": 2.0,
}
VRAM_SAFETY_FACTOR = 1.2
MINIMUM_VRAM_GB = 8.0
BASE_HOURS_PER_BILLION_PARAMS_PER_DATASET_GB = {
    "full_finetuning": 0.12,
    "lora": 0.05,
    "qlora": 0.06,
    "inference": 0.01,
}
DEFAULT_DATASET_SIZE_GB = 1.0
MINIMUM_BASE_HOURS = 0.25

# Model metadata used only as estimation input when the user omits parameter count.
# Values are expressed in billions of parameters and are not runtime measurements.
KNOWN_MODEL_PARAMETER_COUNTS_BILLION = {
    "bert-base-uncased": 0.110,
}
