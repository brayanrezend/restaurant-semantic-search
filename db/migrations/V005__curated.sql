CREATE TABLE IF NOT EXISTS cur_restaurant (
  business_id           VARCHAR2(22) PRIMARY KEY,
  name                  VARCHAR2(400) NOT NULL,
  address               VARCHAR2(400),
  postal_code           VARCHAR2(20),
  latitude              NUMBER NOT NULL,
  longitude             NUMBER NOT NULL,
  geom                  SDO_GEOMETRY,
  stars                 NUMBER(2,1) NOT NULL,
  review_count          NUMBER NOT NULL,
  review_count_declared NUMBER,
  categories            VARCHAR2(4000),
  price_level           NUMBER(1),
  wifi                  VARCHAR2(20),
  alcohol               VARCHAR2(20),
  noise_level           VARCHAR2(20),
  attire                VARCHAR2(20),
  takes_reservations    BOOLEAN,
  outdoor_seating       BOOLEAN,
  good_for_kids         BOOLEAN,
  good_for_groups       BOOLEAN,
  delivery              BOOLEAN,
  takeout               BOOLEAN,
  has_tv                BOOLEAN,
  happy_hour            BOOLEAN,
  dogs_allowed          BOOLEAN,
  wheelchair_accessible BOOLEAN,
  table_service         BOOLEAN,
  byob                  BOOLEAN,
  hours_status          VARCHAR2(10) NOT NULL CHECK (hours_status IN ('OK', 'PARTIAL', 'MISSING')),
  updated_at            TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS cur_restaurant_category (
  business_id VARCHAR2(22) NOT NULL REFERENCES cur_restaurant ON DELETE CASCADE,
  category    VARCHAR2(200) NOT NULL,
  CONSTRAINT cur_restaurant_category_pk PRIMARY KEY (business_id, category)
);

CREATE INDEX IF NOT EXISTS cur_restaurant_category_ix ON cur_restaurant_category (category);

CREATE TABLE IF NOT EXISTS cur_restaurant_hours (
  business_id VARCHAR2(22) NOT NULL REFERENCES cur_restaurant ON DELETE CASCADE,
  day_of_week NUMBER(1) NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
  open_min    NUMBER(4),
  close_min   NUMBER(4),
  slot_status VARCHAR2(10) NOT NULL CHECK (slot_status IN ('NORMAL', 'OVERNIGHT', 'AMBIGUOUS', 'INVALID')),
  CONSTRAINT cur_restaurant_hours_pk PRIMARY KEY (business_id, day_of_week)
);

CREATE TABLE IF NOT EXISTS cur_restaurant_tag (
  business_id VARCHAR2(22) NOT NULL REFERENCES cur_restaurant ON DELETE CASCADE,
  tag_group   VARCHAR2(20) NOT NULL,
  tag         VARCHAR2(40) NOT NULL,
  CONSTRAINT cur_restaurant_tag_pk PRIMARY KEY (business_id, tag_group, tag)
);

INSERT INTO user_sdo_geom_metadata (table_name, column_name, diminfo, srid)
SELECT 'CUR_RESTAURANT', 'GEOM',
       SDO_DIM_ARRAY(SDO_DIM_ELEMENT('X', -180, 180, 0.05), SDO_DIM_ELEMENT('Y', -90, 90, 0.05)), 4326
FROM dual
WHERE NOT EXISTS (SELECT 1 FROM user_sdo_geom_metadata WHERE table_name = 'CUR_RESTAURANT' AND column_name = 'GEOM');

CREATE INDEX IF NOT EXISTS cur_restaurant_geom_sidx ON cur_restaurant (geom) INDEXTYPE IS MDSYS.SPATIAL_INDEX_V2;
