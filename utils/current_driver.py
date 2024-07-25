from threading import Lock

class CurrentDriver:
    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(CurrentDriver, cls).__new__(cls)
                    cls._instance.driver_id = None
        return cls._instance

    def define_driver(self, driver_id):
        self.driver_id = driver_id

    def end_driver_travel(self):
        self.driver_id = None
    
    def get_driver_id(self):
        return self.driver_id

current_driver = CurrentDriver()