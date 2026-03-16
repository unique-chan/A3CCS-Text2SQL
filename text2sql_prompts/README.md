# Text-to-SQL Query Writing Guidelines for Users!

These guidelines help users write clear natural-language queries so that the Text-to-SQL model can generate correct SQL statements.  
Ambiguous or underspecified questions may lead to incorrect SQL generation. Follow the rules below when writing queries.

## 1. Clearly Specify the Entity Being Analyzed

Always specify **the entity level** of the analysis.

👍 Good  
  - "Compute the distance between friendly **vehicles** and enemy **vehicles**."  
  - "Compute the distance between friendly **units** and enemy **units**."

🚫 Bad  
  - "Distance between friendly and enemy forces"  
  - "Compare friendly and enemy positions"

Such queries may cause the model to arbitrarily select a **single representative row**, which leads to incorrect results.


## 2. Explicitly Mention the Data Source (Table)

If possible, specify which table contains the data. If you believe that a query requires JOIN operations across multiple tables, it is recommended to explicitly specify which tables should participate in the JOIN in advance.

👍 Good  
- "Friendly vehicles are stored in the `vehicles` table and enemy vehicles are also in the `vehicles` table."  
- "Friendly units are stored in the `units` table and enemy units are stored in the `units` table."

😐 So so...  
- "Calculate the distance between friendly and enemy vehicles."


## 3. Clearly Define the Time Reference

If the data is time-series, you must explicitly define the **time reference**.

👍 Good  
- "Use the latest `datetime` in the dataset as the reference time."  
- "Friendly forces (side='b') and enemy forces (side='op') may not share the same snapshot time (datetime). For each entity, select the row whose `datetime` is closest to the reference time."

😐 So so... 
- "Use the current position."

The phrase *current* is actually ambiguous and cannot be directly interpreted in SQL.


## 4. Specify the Comparison or Pairing Strategy

Distance or comparison queries must clearly define **how entities are paired**.

Possible pairing strategies:

- All friendly × all enemy (**pairwise distance**)  
- Each friendly entity matched with **its nearest enemy**  
- Distance between **specific IDs**

👍 Good  
- "For each friendly vehicle, find the nearest enemy vehicle and compute the distance. Friendly forces (side='b') and enemy forces (side='op') may not share the same snapshot time (datetime)."

🚫 Bad  
- "Compute the distance between friendly and enemy."


## 5. Define the Output Granularity

Clearly specify what each result row represents and what columns must be included.

👍 Good  

"The result should include:
- `friendly_vehicle_id`
- `enemy_vehicle_id`
- `friendly_datetime`
- `enemy_datetime`
- `distance`"

😐 So so...  

"Output the distance."


## 6. Explicitly State Forbidden Comparisons

If certain comparisons are not allowed due to schema constraints, explicitly state them.

👍 Good  

"Do not use `groups.leaderposx`, `leaderposy`, or `leaderposz` to compute friendly–enemy distances."


## 7. Ask One Analytical Question at a Time

Each query should correspond to **one analytical task**.

👍 Good  

1. "Compute pairwise distances between friendly and enemy vehicles."  
2. "For each friendly vehicle, find the nearest enemy vehicle."

🚫 Bad  

"Compute vehicle distance, find the nearest unit, and calculate time differences."


## Core Principle

A well-formed Text-to-SQL query must clearly specify:

1. **Entity level** (unit, vehicle, group, etc.)
2. **Data source** (which table to use)
3. **Time reference**
4. **Output granularity**

If these four elements are clearly defined, the Text-to-SQL model can generate accurate SQL queries.