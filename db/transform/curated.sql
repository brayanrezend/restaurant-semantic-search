MERGE INTO cur_restaurant t
USING v_restaurant_candidates s
ON (t.business_id = s.business_id)
WHEN MATCHED THEN UPDATE SET
  t.name = s.name, t.address = s.address, t.postal_code = s.postal_code,
  t.latitude = s.latitude, t.longitude = s.longitude,
  t.geom = SDO_GEOMETRY(2001, 4326, SDO_POINT_TYPE(s.longitude, s.latitude, NULL), NULL, NULL),
  t.stars = s.stars, t.review_count = s.review_count, t.review_count_declared = s.review_count_declared,
  t.categories = s.categories, t.price_level = s.price_level, t.wifi = s.wifi, t.alcohol = s.alcohol,
  t.noise_level = s.noise_level, t.attire = s.attire, t.takes_reservations = s.takes_reservations,
  t.outdoor_seating = s.outdoor_seating, t.good_for_kids = s.good_for_kids, t.good_for_groups = s.good_for_groups,
  t.delivery = s.delivery, t.takeout = s.takeout, t.has_tv = s.has_tv, t.happy_hour = s.happy_hour,
  t.dogs_allowed = s.dogs_allowed, t.wheelchair_accessible = s.wheelchair_accessible,
  t.table_service = s.table_service, t.byob = s.byob, t.hours_status = s.hours_status, t.updated_at = SYSTIMESTAMP
WHEN NOT MATCHED THEN INSERT (
  business_id, name, address, postal_code, latitude, longitude, geom, stars, review_count, review_count_declared,
  categories, price_level, wifi, alcohol, noise_level, attire, takes_reservations, outdoor_seating, good_for_kids,
  good_for_groups, delivery, takeout, has_tv, happy_hour, dogs_allowed, wheelchair_accessible, table_service, byob,
  hours_status
) VALUES (
  s.business_id, s.name, s.address, s.postal_code, s.latitude, s.longitude,
  SDO_GEOMETRY(2001, 4326, SDO_POINT_TYPE(s.longitude, s.latitude, NULL), NULL, NULL),
  s.stars, s.review_count, s.review_count_declared, s.categories, s.price_level, s.wifi, s.alcohol, s.noise_level,
  s.attire, s.takes_reservations, s.outdoor_seating, s.good_for_kids, s.good_for_groups, s.delivery, s.takeout,
  s.has_tv, s.happy_hour, s.dogs_allowed, s.wheelchair_accessible, s.table_service, s.byob, s.hours_status
);

DELETE FROM cur_restaurant t
WHERE NOT EXISTS (SELECT 1 FROM v_restaurant_candidates s WHERE s.business_id = t.business_id);

DELETE FROM cur_restaurant_category;

INSERT INTO cur_restaurant_category (business_id, category)
SELECT DISTINCT r.business_id, TRIM(c.category)
FROM cur_restaurant r,
     JSON_TABLE('["' || REPLACE(REPLACE(REPLACE(r.categories, '\', '\\'), '"', '\"'), ', ', '","') || '"]',
                '$[*]' COLUMNS (category VARCHAR2(200) PATH '$')) c
WHERE TRIM(c.category) IS NOT NULL;

DELETE FROM cur_restaurant_hours;

INSERT INTO cur_restaurant_hours (business_id, day_of_week, open_min, close_min, slot_status)
SELECT h.business_id, h.day_of_week,
       CASE WHEN h.slot_status IN ('NORMAL', 'OVERNIGHT') THEN h.open_min END,
       CASE WHEN h.slot_status IN ('NORMAL', 'OVERNIGHT') THEN h.close_min END,
       h.slot_status
FROM v_business_hours h
JOIN cur_restaurant r ON r.business_id = h.business_id;

DELETE FROM cur_restaurant_tag;

INSERT INTO cur_restaurant_tag (business_id, tag_group, tag)
SELECT DISTINCT t.business_id, t.tag_group, t.tag
FROM v_business_tags t
JOIN cur_restaurant r ON r.business_id = t.business_id;
