# Architecture Review & Proposed Improvements

Based on the recent pull, you now have a functional MVP built with Streamlit (`app.py`), a synthetic data generator (`generate_dataset.py`), and pre-generated CSV datasets.

Here is an analysis of the current architecture and proposed next steps to move beyond a static MVP:

## 1. Data Persistence (Database Migration)
**Current:** The app reads from static CSV files. While `generate_dataset.py` can create new data, users cannot interactively adjust stock levels or add new products within the app and have those changes saved.
**Proposed Improvement:** Migrate from CSVs to a lightweight relational database like **SQLite**. 
*   **Why:** SQLite is serverless and stores data in a single `.db` file, making it perfect for this phase.
*   **How:** We can use `SQLAlchemy` (an ORM) to define models for `Stores`, `Products`, `InventoryLogs`, and `TransferCosts`. We would write a script to do a one-time import of your CSV data into the SQLite database. `app.py` would then be updated to query the database instead of reading CSVs.

## 2. Interactive Data Entry UI
**Current:** The Streamlit sidebar only has filters (dates, thresholds). It is purely a read-only analysis tool.
**Proposed Improvement:** Add "Data Management" tabs/pages to the Streamlit app.
*   **What to add:** 
    *   A form to "Receive Shipment" (increases stock for a store/product).
    *   A form to "Log Manual Sale" (decreases stock).
    *   A view to edit `product_master` details (like unit cost/margin).
*   **Why:** This transforms the app from a static calculator into an operational tool that a warehouse manager could actually use daily.

## 3. Transfer Execution (State Management)
**Current:** The app recommends transfers (e.g., "Move 10 units of P01 from S1 to S2") and calculates profit, but there is no way to "accept" the recommendation.
**Proposed Improvement:** Add a "Pending Transfers" workflow.
*   **How:** 
    1.  Add an "Execute" button next to top recommendations in the UI.
    2.  When clicked, it writes a record to a new `Transfers` table in the database (Status: Pending or Completed).
    3.  It automatically deducts 10 units from S1's inventory and adds 10 to S2's inventory in the database.
*   **Why:** Closes the loop. The system isn't just suggesting actions; it's tracking them.

## 4. Advanced Forecasting Validation
**Current:** The forecast strategy in `forecast.py` is a simple moving average with day-of-week multipliers.
**Proposed Improvement:** Build an accuracy tracker.
*   **How:** Since we have 30 days of historical data, we can run the algorithm as if today was day 20, let it forecast days 21-27, and then compare its forecast against the *actual* sales that happened on days 21-27. 
*   **Why:** Before trusting an algorithm to move thousands of dollars of stock, business stakeholders will want proof that the forecasting engine is accurate.

## Immediate Next Steps (Pick One to Start):
1.  **Database Build:** We convert the CSVs to a SQLite database and hook it up to the existing Python scripts.
2.  **UI Data Entry:** We build forms in Streamlit to let you manually add/remove stock.
3.  **UI Execution:** We add buttons to explicitly "Accept" transfer recommendations.
