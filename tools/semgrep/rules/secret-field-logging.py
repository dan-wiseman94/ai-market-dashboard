# Test fixture for secret-field-logging. Run: semgrep --test --config <dir>
import logging

logger = logging.getLogger(__name__)


def _fixture(cfg):
    # ruleid: secret-field-logging
    logger.info("key=%s", cfg._api_key)
    # ruleid: secret-field-logging
    logger.warning(f"using {cfg._api_key}")
    # ruleid: secret-field-logging
    print("debug", cfg._api_key)
    # ruleid: secret-field-logging
    logger.debug("tok", cfg.access_token)
    # ok: secret-field-logging
    logger.info("connected provider=%s", cfg.provider)
    # ok: secret-field-logging
    key = cfg._api_key
    return key
