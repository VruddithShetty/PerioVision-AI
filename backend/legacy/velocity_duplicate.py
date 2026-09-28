import datetime

class ProgressionVelocityCalculator:
    """
    Computes the rate of bone loss over time (mm or % per year).
    """
    
    def calculate_velocity(self, history):
        """
        history: list of {'date': iso_str, 'bl_pct': float}
        """
        if len(history) < 2:
            return 0.0
            
        # Sort by date
        history.sort(key=lambda x: x["date"])
        
        d1 = datetime.datetime.fromisoformat(history[0]["date"].replace('Z', '+00:00'))
        d2 = datetime.datetime.fromisoformat(history[-1]["date"].replace('Z', '+00:00'))
        
        years = (d2 - d1).days / 365.25
        if years < 0.1: return 0.0
        
        bl_diff = history[-1]["bl_pct"] - history[0]["bl_pct"]
        return round(bl_diff / years, 3)
