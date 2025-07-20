from prometheus_client import Gauge, Counter, start_http_server

class Exporter:
    def __init__(self, port=9105):
        # gauges
        self.power_before   = Gauge("optimiser_power_before_w",  "Total Watts before action")
        self.power_after    = Gauge("optimiser_power_after_w",   "Total Watts after action")
        self.savings_total  = Counter("optimiser_cumulative_w",  "Cumulative Watts saved")
        self.last_action    = Gauge("optimiser_last_action_id",  "0=none,1=consolidate,…")
        start_http_server(port)

    def record(self, before, after, action_id):
        self.power_before.set(before); self.power_after.set(after)
        if before > after:
            self.savings_total.inc(before-after)
        self.last_action.set(action_id)
