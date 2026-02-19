"""
ID generation utilities for ACE Enterprise entities.
Based on PRD naming conventions.
"""
import random
import string
from datetime import datetime


def generate_playbook_id() -> str:
    """
    Generate unique playbook ID.
    Format: pb_YYYYMMDD_NNN
    Example: pb_20251016_001
    """
    date_str = datetime.utcnow().strftime("%Y%m%d")
    random_num = random.randint(1, 999)
    return f"pb_{date_str}_{random_num:03d}"


def generate_bullet_id(sequence: int) -> str:
    """
    Generate unique bullet ID.
    Format: ctx-NNNNN
    Example: ctx-00001

    Args:
        sequence: Sequential number for the bullet
    """
    return f"ctx-{sequence:05d}"


def generate_experiment_id() -> str:
    """
    Generate unique experiment ID.
    Format: exp_YYYYMMDD_NNNNN
    Example: exp_20251016_12345
    """
    date_str = datetime.utcnow().strftime("%Y%m%d")
    random_num = random.randint(1, 99999)
    return f"exp_{date_str}_{random_num:05d}"


def generate_checkpoint_id() -> str:
    """
    Generate unique checkpoint ID.
    Format: ckpt_YYYYMMDD_NNN
    Example: ckpt_20251016_003
    """
    date_str = datetime.utcnow().strftime("%Y%m%d")
    random_num = random.randint(1, 999)
    return f"ckpt_{date_str}_{random_num:03d}"


def generate_task_id() -> str:
    """
    Generate unique task ID.
    Format: task_NNNNN
    Example: task_12345
    """
    random_num = random.randint(1, 99999)
    return f"task_{random_num:05d}"


def generate_confirmation_token(length: int = 8) -> str:
    """
    Generate a random confirmation token for critical operations.

    Args:
        length: Length of token (default 8)

    Returns:
        Random alphanumeric string
    """
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))
