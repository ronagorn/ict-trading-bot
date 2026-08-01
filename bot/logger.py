import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger(name="ict_bot"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # ป้องกันการซ้ำซ้อนถ้ามีการเรียก setup_logger หลายครั้ง
    if not logger.handlers:
        log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Console Handler
        c_handler = logging.StreamHandler()
        c_handler.setLevel(logging.INFO)
        c_handler.setFormatter(log_format)
        logger.addHandler(c_handler)

        # File Handler
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        f_handler = RotatingFileHandler(f"{log_dir}/trading_bot.log", maxBytes=5*1024*1024, backupCount=2, encoding='utf-8')
        f_handler.setLevel(logging.DEBUG)
        f_handler.setFormatter(log_format)
        logger.addHandler(f_handler)

    return logger

logger = setup_logger()
