from threading import Lock

class TravelState:
    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(TravelState, cls).__new__(cls)
                    cls._instance.is_traveling = False
        return cls._instance

    def start_travel(self):
        self.is_traveling = True

    def end_travel(self):
        self.is_traveling = False

    def get_travel_status(self):
        return self.is_traveling

travel_state = TravelState()