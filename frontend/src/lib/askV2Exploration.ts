import type {
  AskV2CanonicalEntity,
  AskV2ResolvedEntity,
  AskV2Response,
  AskV2SeasonContext,
} from "../api/askV2";

export interface AskV2ExploreAction {
  id: string;
  kind: "navigate" | "ask";
  label: string;
  description: string;
  href?: string;
  question?: string;
  entities: AskV2CanonicalEntity[];
  seasons?: AskV2SeasonContext;
}

function canonical(entity: AskV2ResolvedEntity): AskV2CanonicalEntity {
  return { kind: entity.kind, id: entity.id };
}

function possessive(name: string) {
  return name.endsWith("s") ? `${name}'` : `${name}'s`;
}

function addQuery(
  path: string,
  values: Record<string, string | number | undefined>,
) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined) query.set(key, String(value));
  }
  return `${path}?${query.toString()}`;
}

export function responseSeasonContext(
  response: AskV2Response,
): AskV2SeasonContext | undefined {
  const seasons = [
    ...new Set(
      response.propositions
        .map((proposition) => proposition.season)
        .filter((season): season is number => season !== null),
    ),
  ].sort((left, right) => left - right);
  if (seasons.length === 0) return undefined;
  return {
    start_season: seasons[0],
    end_season: seasons[seasons.length - 1],
  };
}

function explorerHref(
  entities: readonly AskV2ResolvedEntity[],
  seasons: AskV2SeasonContext | undefined,
): string | undefined {
  const qbs = entities.filter((entity) => entity.kind === "qb");
  const qb = qbs[0];
  const coach = entities.find((entity) => entity.kind === "coach");
  const team = entities.find((entity) => entity.kind === "team");
  const historicalSeasons = observedSeasonContext(seasons);
  const seasonValues = {
    start_season: historicalSeasons.start_season,
    end_season: historicalSeasons.end_season,
  };

  if (team) {
    const selected = qb
      ? `qb:${qb.id}`
      : coach
        ? `coach:${coach.id}`
        : historicalSeasons.start_season === historicalSeasons.end_season
          ? `team-season:${team.id}:${historicalSeasons.start_season}`
          : undefined;
    return addQuery("/network", {
      mode: "team_history",
      team_id: team.id,
      ...seasonValues,
      ...(selected ? { selected } : {}),
    });
  }
  if (qb && coach) {
    const endSeason = historicalSeasons.end_season;
    const startSeason = Math.max(historicalSeasons.start_season, endSeason - 4);
    return addQuery("/network", {
      mode: "full_network",
      anchor: "qb",
      player_id: qb.id,
      start_season: startSeason,
      end_season: endSeason,
      selected: `qb:${qb.id}`,
    });
  }
  if (qb) {
    return addQuery("/network", {
      mode: "qb_journey",
      player_id: qb.id,
      ...seasonValues,
      selected: `qb:${qb.id}`,
    });
  }
  if (coach) {
    return addQuery("/network", {
      mode: "coach_journey",
      coach_id: coach.id,
      ...seasonValues,
      selected: `coach:${coach.id}`,
    });
  }
  return undefined;
}

function observedSeasonContext(
  seasons: AskV2SeasonContext | undefined,
): AskV2SeasonContext {
  if (!seasons || seasons.start_season > 2025 || seasons.end_season < 2010)
    return { start_season: 2010, end_season: 2025 };
  return {
    start_season: Math.max(2010, seasons.start_season),
    end_season: Math.min(2025, seasons.end_season),
  };
}

function fullNetworkHref(
  entities: readonly AskV2ResolvedEntity[],
  seasons: AskV2SeasonContext | undefined,
  response: AskV2Response,
) {
  const people = entities.filter(
    (entity) => entity.kind === "qb" || entity.kind === "coach",
  );
  if (people.length < 2) return undefined;
  const historicalSeasons = observedSeasonContext(seasons);
  // A retired player's recorded season must not be silently replaced by a window
  // containing only the other participant. Scope the main pair's observed history.
  const observedEnds = people.slice(0, 2).flatMap((entity) => {
    const years = response.propositions
      .filter((item) => item.subject === entity.display_name)
      .map((item) => item.season)
      .filter(
        (year): year is number => year !== null && year >= 2010 && year <= 2025,
      );
    return years.length ? [Math.max(...years)] : [];
  });
  const endSeason = Math.min(historicalSeasons.end_season, ...observedEnds);
  const startSeason = Math.max(historicalSeasons.start_season, endSeason - 4);
  const nodeIds = people.map((entity) =>
    entity.kind === "qb" ? `qb:${entity.id}` : `coach:${entity.id}`,
  );
  return addQuery("/network", {
    mode: "full_network",
    anchor: "all",
    start_season: startSeason,
    end_season: endSeason,
    selected: nodeIds[0],
    highlights: nodeIds.slice(0, 8).join(","),
  });
}

function profileHref(entity: AskV2ResolvedEntity): string | undefined {
  if (entity.kind === "qb") return `/qbs/${encodeURIComponent(entity.id)}`;
  if (entity.kind === "coach")
    return `/coaches/${encodeURIComponent(entity.id)}`;
  return undefined;
}

function statisticsHref(
  qb: AskV2ResolvedEntity,
  seasons: AskV2SeasonContext | undefined,
) {
  return addQuery("/statistics", {
    player: qb.display_name,
    ...(seasons &&
    seasons.start_season === seasons.end_season &&
    seasons.end_season <= 2025 &&
    seasons.start_season >= 2010
      ? { season: seasons.start_season }
      : {}),
  });
}

function actionKey(action: AskV2ExploreAction) {
  return `${action.kind}:${action.href ?? action.question ?? action.label}`;
}

export function buildKeepExploringActions(
  response: AskV2Response,
): AskV2ExploreAction[] {
  if (response.answerability === "CLARIFICATION_REQUIRED") return [];
  const entities = response.entities;
  const canonicalEntities = entities.map(canonical);
  const seasons = responseSeasonContext(response);
  const qbs = entities.filter((entity) => entity.kind === "qb");
  const qb = qbs[0];
  const coaches = entities.filter((entity) => entity.kind === "coach");
  const team = entities.find((entity) => entity.kind === "team");
  const candidates: AskV2ExploreAction[] = [];
  const add = (action: AskV2ExploreAction) => candidates.push(action);

  const addJourney = (entity: AskV2ResolvedEntity) => {
    const href = explorerHref([entity], seasons);
    if (!href) return;
    add({
      id: `${entity.kind}-journey:${entity.id}`,
      kind: "navigate",
      label:
        entity.kind === "qb"
          ? `View ${possessive(entity.display_name)} career tree`
          : entity.kind === "coach"
            ? `View ${possessive(entity.display_name)} coach tree`
            : `View ${entity.display_name} history`,
      description:
        entity.kind === "team"
          ? "Open chronological team-season context."
          : "Trace teams, seasons, and coaching context.",
      href,
      entities: [canonical(entity)],
      ...(seasons ? { seasons } : {}),
    });
  };

  if (qbs.length >= 2) {
    addJourney(qbs[0]);
    addJourney(qbs[1]);
  } else if (qb && coaches[0]) {
    addJourney(qb);
    addJourney(coaches[0]);
  } else if (qb && team) {
    addJourney(qb);
    addJourney(team);
  } else if (coaches.length >= 2) {
    addJourney(coaches[0]);
    addJourney(coaches[1]);
  } else if (coaches[0] && team) {
    addJourney(coaches[0]);
    addJourney(team);
  } else if (qb) {
    addJourney(qb);
    add({
      id: `qb-statistics:${qb.id}`,
      kind: "navigate",
      label:
        seasons &&
        seasons.start_season === seasons.end_season &&
        seasons.end_season <= 2025 &&
        seasons.start_season >= 2010
          ? `View ${possessive(qb.display_name)} ${seasons.start_season} statistics`
          : `View ${possessive(qb.display_name)} statistics`,
      description: "Open published quarterback season statistics.",
      href: statisticsHref(qb, seasons),
      entities: [canonical(qb)],
      ...(seasons ? { seasons } : {}),
    });
  } else if (coaches[0]) {
    addJourney(coaches[0]);
    add({
      id: `coach-profile:${coaches[0].id}`,
      kind: "navigate",
      label: `Open ${possessive(coaches[0].display_name)} profile`,
      description: "Review verified roles, intervals, and QB contexts.",
      href: profileHref(coaches[0]),
      entities: [canonical(coaches[0])],
      ...(seasons ? { seasons } : {}),
    });
  } else if (team) {
    addJourney(team);
    add({
      id: `team-statistics:${team.id}`,
      kind: "navigate",
      label: `View ${team.display_name} statistics`,
      description: "Open published team and quarterback statistics.",
      href: addQuery("/statistics", {
        team: team.id,
        ...(seasons && seasons.start_season === seasons.end_season
          ? { season: seasons.start_season }
          : {}),
      }),
      entities: [canonical(team)],
      ...(seasons ? { seasons } : {}),
    });
  }

  const relationshipHref =
    qbs.length + coaches.length >= 2
      ? fullNetworkHref(entities, seasons, response)
      : qb && team
        ? explorerHref([qb, team], seasons)
        : coaches[0] && team
          ? explorerHref([coaches[0], team], seasons)
          : undefined;
  if (relationshipHref) {
    add({
      id: "relationship-explorer",
      kind: "navigate",
      label:
        entities.length > 1
          ? `Explore ${entities
              .slice(0, 2)
              .map((entity) => entity.display_name)
              .join(" + ")}`
          : "Explore the relationship context",
      description:
        "Open supported history; entities appear only where observed.",
      href: relationshipHref,
      entities: canonicalEntities,
      ...(seasons ? { seasons } : {}),
    });
  }

  const addBackendFollowUps = () => {
    for (const followUp of response.follow_ups.slice(0, 1))
      add({
        id: `follow-up:${followUp.question}`,
        kind: "ask",
        label: followUp.label,
        description: "Continue this conversation with the same entities.",
        question: followUp.question,
        entities: canonicalEntities,
        ...(seasons ? { seasons } : {}),
      });
  };
  if (qbs.length < 2 && coaches.length < 2) addBackendFollowUps();

  if (qbs.length >= 2) {
    add({
      id: "follow-up:qb-comparison-context",
      kind: "ask",
      label: "Compare the coaches around their best seasons",
      description: "Continue with both quarterbacks in canonical context.",
      question: `Which coaches were involved in ${possessive(qbs[0].display_name)} and ${possessive(qbs[1].display_name)} best seasons?`,
      entities: canonicalEntities,
      ...(seasons ? { seasons } : {}),
    });
    add({
      id: "follow-up:qb-connection",
      kind: "ask",
      label: "Where do their histories connect?",
      description: "Trace shared team and coaching context where supported.",
      question: `Where do ${possessive(qbs[0].display_name)} and ${possessive(qbs[1].display_name)} histories connect?`,
      entities: canonicalEntities,
      ...(seasons ? { seasons } : {}),
    });
  } else if (coaches.length >= 2) {
    add({
      id: "follow-up:coach-evidence",
      kind: "ask",
      label: `Which QB histories connect to ${coaches[0].display_name}?`,
      description: "Continue with historical context, not causal attribution.",
      question: `Which quarterbacks shared ${possessive(coaches[0].display_name)} team-seasons?`,
      entities: canonicalEntities,
      ...(seasons ? { seasons } : {}),
    });
  } else if (qb && team) {
    add({
      id: "follow-up:alignment-limit",
      kind: "ask",
      label: "What is descriptive here?",
      description: "Separate observed alignment from unsupported prediction.",
      question: "Which parts are descriptive rather than predictive?",
      entities: canonicalEntities,
      ...(seasons ? { seasons } : {}),
    });
  } else if (qb) {
    add({
      id: "follow-up:qb-coaches",
      kind: "ask",
      label: `Which coaches were involved in ${possessive(qb.display_name)} best seasons?`,
      description: "Review verified coaching context around peak seasons.",
      question: `Who was coaching ${qb.display_name} during his best seasons?`,
      entities: [canonical(qb)],
      ...(seasons ? { seasons } : {}),
    });
  } else if (coaches[0]) {
    add({
      id: "follow-up:coach-context",
      kind: "ask",
      label: `Which QB contexts are verified?`,
      description: `Review source-backed context for ${coaches[0].display_name}.`,
      question: `Which quarterback contexts are directly verified for ${coaches[0].display_name}?`,
      entities: [canonical(coaches[0])],
      ...(seasons ? { seasons } : {}),
    });
  } else if (team) {
    add({
      id: "follow-up:team-scheme",
      kind: "ask",
      label: "How did the offense change?",
      description: `Continue with ${possessive(team.display_name)} historical scheme.`,
      question: `How did ${possessive(team.display_name)} offense change across seasons?`,
      entities: [canonical(team)],
      ...(seasons ? { seasons } : {}),
    });
  }

  if (qbs.length >= 2 || coaches.length >= 2) addBackendFollowUps();

  if (canonicalEntities.length > 0) {
    add({
      id: "follow-up:explain",
      kind: "ask",
      label: "Explain the result",
      description: "Ask for a plain-language explanation of this answer.",
      question: "Why?",
      entities: canonicalEntities,
      ...(seasons ? { seasons } : {}),
    });
  }

  const unique = new Map<string, AskV2ExploreAction>();
  for (const action of candidates) {
    const key = actionKey(action);
    if (!unique.has(key)) unique.set(key, action);
  }
  return [...unique.values()].slice(0, 4);
}
