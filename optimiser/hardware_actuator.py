import subprocess, os, logging
GOVERNOR = os.getenv("CPU_GOV", "powersave")      # or "schedutil"

def set_cpufreq(governor: str = GOVERNOR):
    try:
        subprocess.run(
            ["cpupower", "frequency-set", "-g", governor],
            check=True, capture_output=True)
        logging.info(f"cpufreq governor set → {governor}")
        return True
    except Exception as e:
        logging.error("cpufreq set failed: %s", e)
        return False

def set_rapl(limit_watts: int):
    try:
        with open("/sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw", "w") as f:
            f.write(str(limit_watts * 1_000_000))
        logging.info("RAPL limit set → %d W", limit_watts)
        return True
    except Exception as e:
        logging.error("RAPL write failed: %s", e); return False
if __name__ == "__main__":
    # Runs once in the DaemonSet container
    ok1 = set_cpufreq()
    ok2 = set_rapl()
    status = "SUCCESS" if ok1 or ok2 else "NO-ACTION"
    open("/tmp/node-tuner.status", "w").write(f"{status} {time.time()}\n")
