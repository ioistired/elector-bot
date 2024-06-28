-- :macro create_election()
INSERT INTO elections (guild_id, creator_id)
VALUES ($1, $2)
RETURNING election_id
-- :endmacro

-- :macro submit_ballot()
INSERT INTO ballots (election_id, user_id, ballot)
VALUES ($1, $2, $3)
-- :endmacro

-- :macro check_if_voted()
SELECT 1
FROM ballots
WHERE user_id = $1 AND election_id = $2
-- :endmacro

-- :macro get_ballots()
SELECT ballot, COUNT(ballot) AS weight
FROM ballots
WHERE election_id = $1
GROUP BY ballot
-- :endmacro
