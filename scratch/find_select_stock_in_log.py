import csv

csv_path = r"C:\Users\User\Downloads\stk_wn1430.csv"
try:
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)
        print("Total rows:", len(rows))
        
        # Extract unique dates
        dates = []
        for row in rows[1:]:
            if row:
                dates.append(row[0])
        print("Unique dates count:", len(set(dates)))
        print("Dates in CSV:", sorted(list(set(dates))))
        
        print("\nFirst 10 records:")
        for r in rows[:10]:
            print(r)
except Exception as e:
    print("Error:", e)
