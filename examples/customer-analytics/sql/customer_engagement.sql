-- Reference transformation owned by the example project.
SELECT
    customers.customer_id,
    customers.email,
    COUNT(events.event_id) AS event_count,
    MAX(events.occurred_at) AS last_event_at
FROM raw_customers AS customers
LEFT JOIN raw_customer_events AS events
    ON customers.customer_id = events.customer_id
GROUP BY customers.customer_id, customers.email
