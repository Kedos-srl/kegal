## Graph Response
 * Token Input size: 370
 * Token Output size: 422
 * Compile time: 17.54109263420105
### Node:  query_node
```json
 [
    {
        "name": "query_db",
        "parameters": {
            "sql": "SELECT product, quarter, revenue FROM sales ORDER BY product, quarter;"
        }
    }
] 
```
```
product, quarter, revenue
Widget A, Q1, 12500.0
Widget A, Q2, 15200.0
Widget A, Q3, 13800.0
Widget A, Q4, 17100.0
Widget B, Q1, 8300.0
Widget B, Q2, 11400.0
Widget B, Q3, 9600.0
Widget B, Q4, 12000.0
Widget C, Q2, 4700.0
Widget C, Q3, 6200.0
Widget C, Q4, 8900.0
```

Token Input size:  139 
  Token Output size:  24 
 ### Node:  analyst_node

Token Input size:  231 
  Token Output size:  398 
 