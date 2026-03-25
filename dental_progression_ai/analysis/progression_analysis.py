def analyze_progression(historical_records, current_bone_loss):
    """
    Compares the current bone loss against historical records.
    Returns a longitudinal progression table data structure.
    
    historical_records: List of dictionaries from xrays sorted chronologically.
    current_bone_loss: Dictionary mapped by tooth_number with current %
    """
    progression_table = []
    
    # Extract historical timeline keys
    analysis_dates = [rec["analysis_date"] for rec in historical_records]
    
    for tooth_num, current_loss in current_bone_loss.items():
        row = {"Tooth": tooth_num}
        
        # Populate history
        previous_loss = None
        for rec in historical_records:
            date_str = rec["analysis_date"]
            loss_at_date = rec["bone_loss_results"].get(tooth_num, "N/A")
            row[date_str] = loss_at_date
            if loss_at_date != "N/A":
                previous_loss = float(loss_at_date)
                
        # Populate Current
        row["Current"] = current_loss
        
        # Calculate Change (Current - Most Recent Historic)
        change_str = "0%"
        if previous_loss is not None:
            change = current_loss - previous_loss
            sign = "+" if change >= 0 else ""
            change_str = f"{sign}{round(change, 1)}%"
        else:
            change_str = "N/A"
            
        row["Change"] = change_str
        progression_table.append(row)
        
    return progression_table
