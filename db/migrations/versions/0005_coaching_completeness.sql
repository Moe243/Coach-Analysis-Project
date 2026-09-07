DROP VIEW api_coaching_completeness;

ALTER TABLE serving_coaching_completeness
    DROP CONSTRAINT serving_coaching_completeness_assignment_status_check;

UPDATE serving_coaching_completeness
SET assignment_status = CASE assignment_status
    WHEN 'missing' THEN 'unresolved'
    ELSE assignment_status
END;

ALTER TABLE serving_coaching_completeness
    ADD COLUMN evidence_version text NOT NULL DEFAULT 'legacy',
    ADD COLUMN source_urls jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN evidence_intervals jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD CONSTRAINT serving_coaching_completeness_assignment_status_check
        CHECK (assignment_status IN (
            'verified',
            'verified_no_designated_role',
            'partial',
            'provisional',
            'conflicting',
            'unresolved'
        )),
    ADD CONSTRAINT serving_coaching_completeness_source_urls_array_check
        CHECK (jsonb_typeof(source_urls) = 'array'),
    ADD CONSTRAINT serving_coaching_completeness_evidence_intervals_array_check
        CHECK (jsonb_typeof(evidence_intervals) = 'array'),
    ADD CONSTRAINT serving_coaching_completeness_no_role_provenance_check
        CHECK (
            assignment_status <> 'verified_no_designated_role'
            OR (
                assignment_count = 0
                AND verified_assignment_count = 0
                AND jsonb_array_length(source_urls) > 0
                AND jsonb_array_length(evidence_intervals) > 0
            )
        );

CREATE VIEW api_coaching_completeness AS
SELECT c.*, t.team_abbr, t.team_name
FROM serving_coaching_completeness c
JOIN serving_publication p ON p.load_id = c.load_id
JOIN serving_teams t ON t.load_id = c.load_id AND t.team_id = c.team_id;
