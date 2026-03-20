from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any

class BaseDataIngestor(ABC):
    """基础数据采集器抽象类"""
    
    def __init__(self, source_name: str):
        self.source_name = source_name
        self.last_fetch_time = None
    
    @abstractmethod
    def fetch_data(self) -> Dict[str, Any]:
        """采集数据的抽象方法，子类必须实现"""
        pass
    
    def preprocess(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """数据预处理，可被子类重写"""
        data["updated_at"] = datetime.utcnow()
        return data
    
    def run(self) -> Dict[str, Any]:
        """运行一次采集"""
        try:
            raw_data = self.fetch_data()
            processed_data = self.preprocess(raw_data)
            self.last_fetch_time = datetime.utcnow()
            return {
                "success": True,
                "source": self.source_name,
                "data": processed_data,
                "fetch_time": self.last_fetch_time
            }
        except Exception as e:
            return {
                "success": False,
                "source": self.source_name,
                "error": str(e),
                "fetch_time": datetime.utcnow()
            }
