import logging

# 로거 설정
#logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
#logger = logging.getLogger(__name__)

class Logger: 
    _logger = None
    _handler = None
    
    @staticmethod
    def getLogger():
        if Logger._logger is None:
            Logger._logger = logging.getLogger("SRTConverterLogger")
            Logger._logger.setLevel(logging.INFO)
            
            # 기본 핸들러 설정
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            Logger._logger.addHandler(handler)
        
        return Logger._logger
    
    @staticmethod
    def setUITextEdit(handler):
        if Logger._handler:
            Logger._logger.removeHandler(Logger._handler)
        
        Logger._handler = handler
        Logger.getLogger().addHandler(Logger._handler)


    @staticmethod
    def info(msg):
        Logger.getLogger().info(msg)
    
    @staticmethod
    def error(msg):
        Logger.getLogger().error(msg)
    
    @staticmethod
    def warning(msg):
        Logger.getLogger().warning(msg)
    
    @staticmethod
    def fatal(msg):
        Logger.getLogger().fatal(msg)
    
    @staticmethod
    def debug(msg):
        Logger.getLogger().debug(msg)
