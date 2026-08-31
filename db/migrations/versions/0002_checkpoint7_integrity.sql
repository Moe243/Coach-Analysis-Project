CREATE FUNCTION enforce_serving_assignment_exposure_lineage()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM serving_coach_exposures exposure
         WHERE exposure.load_id = NEW.load_id
           AND exposure.assignment_key = NEW.assignment_key
           AND (exposure.coach_id <> NEW.coach_id
                OR exposure.team_id <> NEW.team_id
                OR exposure.season <> NEW.season
                OR exposure.role <> NEW.role
                OR exposure.start_week <> NEW.start_week
                OR exposure.end_week <> NEW.end_week
                OR exposure.verification_status <> NEW.verification_status
                OR exposure.confidence_level <> NEW.confidence_level
                OR exposure.interval_basis <> NEW.interval_basis
                OR exposure.is_shared <> NEW.is_shared)
    ) THEN
        RAISE EXCEPTION 'coach assignment must match exposure lineage';
    END IF;
    RETURN NEW;
END;
$$;

CREATE CONSTRAINT TRIGGER serving_assignment_exposure_lineage_guard
AFTER UPDATE OF coach_id, team_id, season, role, start_week, end_week,
                verification_status, confidence_level, interval_basis, is_shared
ON serving_coach_assignments
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION enforce_serving_assignment_exposure_lineage();
