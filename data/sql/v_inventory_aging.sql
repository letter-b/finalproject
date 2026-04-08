DROP VIEW IF EXISTS `v_inventory_aging`;
CREATE VIEW `v_inventory_aging` AS SELECT p.product_id, p.product_name, p.brand, p.listed_date, p.rental_eligible_date, DATEDIFF(CURDATE(), p.listed_date) AS days_on_shelf, p.original_retail_price, p.current_depreciated_value, c.category_name, c.depreciation_class FROM products p JOIN categories c ON p.category_id = c.category_id;
