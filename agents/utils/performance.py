import time
from datetime import datetime

class PerformanceTracker:
    def __init__(self):
        self.metrics = {}
        self.start_time = time.time()

    def start_phase(self, phase_name):
        self.metrics[phase_name] = {
            "start": time.time(),
            "status": "Running",
            "end": None,
            "duration": None,
            "jobs_applied": 0,
            "error": None
        }
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Started Agent Phase: {phase_name}")

    def end_phase(self, phase_name, jobs_applied=0, error=None):
        if phase_name in self.metrics:
            m = self.metrics[phase_name]
            m["end"] = time.time()
            m["duration"] = m["end"] - m["start"]
            m["jobs_applied"] = jobs_applied
            m["error"] = error
            m["status"] = "Error" if error else "Success"
            
            status_icon = "❌" if error else "✅"
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {status_icon} Finished Agent Phase: {phase_name} | Duration: {m['duration']:.2f}s | Applied: {jobs_applied}")

    def summary(self):
        print("\n" + "="*60)
        print("📊 MULTI-AGENT PERFORMANCE SUMMARY")
        print("="*60)
        total_time = time.time() - self.start_time
        print(f"Total Orchestration Time: {total_time:.2f}s")
        print("-" * 60)
        
        total_applied = 0
        for name, m in self.metrics.items():
            dur = f"{m['duration']:.2f}s" if m['duration'] else "Running"
            err = f" | Error: {m['error']}" if m['error'] else ""
            status = m['status']
            applied = m['jobs_applied']
            total_applied += applied
            print(f"  {name.ljust(25)} {status.ljust(10)} {dur.ljust(10)} {applied} jobs {err}")
            
        print("-" * 60)
        print(f"Total Jobs Applied Across All Agents: {total_applied}")
        print("="*60 + "\n")


class CostOptimizer:
    def __init__(self):
        """
        Approximates Gemini API costs.
        Based on gemini-2.0-flash pricing (example rates, update as needed):
        Input: $0.075 / 1M tokens
        Output: $0.30 / 1M tokens
        """
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        
        # In dollars
        self.input_cost_per_m = 0.075
        self.output_cost_per_m = 0.30

    def log_usage(self, input_chars, output_chars):
        """
        Rough heuristic: 1 token ~= 4 chars of English text.
        We use this to estimate token usage when the API object doesn't return exact counts.
        """
        est_in_tokens = len(input_chars) // 4
        est_out_tokens = len(output_chars) // 4
        
        self.total_input_tokens += est_in_tokens
        self.total_output_tokens += est_out_tokens
        
    def add_tokens(self, input_tokens, output_tokens):
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    def get_estimated_cost(self):
        in_cost = (self.total_input_tokens / 1_000_000) * self.input_cost_per_m
        out_cost = (self.total_output_tokens / 1_000_000) * self.output_cost_per_m
        return in_cost + out_cost

    def summary(self):
        cost = self.get_estimated_cost()
        print("\n" + "="*40)
        print("💰 GEN-AI COST OPTIMIZATION TRACKER")
        print("="*40)
        print(f"Input Tokens:  ~{self.total_input_tokens:,}")
        print(f"Output Tokens: ~{self.total_output_tokens:,}")
        print(f"Est. Total Cost: ${cost:.5f} USD")
        print("="*40 + "\n")

# Global singleton so easily imported
PERFORMANCE_TRACKER = PerformanceTracker()
COST_OPTIMIZER = CostOptimizer()
