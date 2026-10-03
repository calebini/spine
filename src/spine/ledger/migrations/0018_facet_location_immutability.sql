DROP TRIGGER locations_referenced_canonical_fields_update;

CREATE TRIGGER locations_referenced_canonical_fields_update
BEFORE UPDATE OF label, kind, address_text, latitude, longitude, timezone, provider_ref ON locations
FOR EACH ROW
WHEN EXISTS (SELECT 1 FROM item_locations WHERE location_id = OLD.location_id)
  OR EXISTS (SELECT 1 FROM item_facet_references WHERE location_id = OLD.location_id)
BEGIN
  SELECT RAISE(ABORT, 'referenced location canonical fields are immutable');
END;
