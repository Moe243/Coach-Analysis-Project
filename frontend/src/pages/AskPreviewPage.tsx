import { RotateCcw } from "lucide-react";
import { AskComposer } from "../components/askV2/AskComposer";
import { AskV2AssistantTurn } from "../components/askV2/AskV2AssistantTurn";
import { useAskV2Conversation } from "../hooks/useAskV2Conversation";
import "./AskPreviewPage.css";

const examples = [
  "How did Josh Allen perform in 2022?",
  "Is Lamar Jackson mobile?",
  "Compare Andy Reid and Mike Tomlin with quarterbacks.",
  "What type of offense did Miami run in 2024?",
  "What does the model project for Josh Allen in 2026?",
  "How would Kyler Murray fit Minnesota?",
];

export function AskPreviewPage() {
  const conversation = useAskV2Conversation();
  return (
    <section className="page ask-v2-page">
      <header className="ask-v2-page-header">
        <div>
          <p className="eyebrow">Evidence-led football analysis</p>
          <h1>Ask Anything</h1>
          <p>
            Ask questions about quarterbacks, coaches, historical schemes,
            projections, and the evidence behind them.
          </p>
        </div>
        {conversation.turns.length > 0 && (
          <button
            className="button button-secondary"
            type="button"
            onClick={conversation.reset}
          >
            <RotateCcw aria-hidden="true" /> New conversation
          </button>
        )}
      </header>

      {conversation.turns.length === 0 && (
        <section
          className="ask-v2-welcome"
          aria-labelledby="ask-v2-start-heading"
        >
          <div>
            <span>Evidence-led conversation</span>
            <h2 id="ask-v2-start-heading">
              Start with a question the project can answer
            </h2>
            <p>
              Historical facts, measured style, scheme context, and
              team-independent projections are available. When only part of a
              question is supported, you will still get the useful evidence
              first.
            </p>
          </div>
          <div className="ask-v2-example-grid">
            {examples.map((example) => (
              <button
                type="button"
                key={example}
                onClick={() => conversation.submit(example)}
              >
                <span>Try asking</span>
                {example}
              </button>
            ))}
          </div>
        </section>
      )}

      {conversation.turns.length > 0 && (
        <section
          className="ask-v2-transcript"
          aria-label="Ask Anything conversation"
        >
          {conversation.turns.map((turn, index) => (
            <div className="ask-v2-exchange" key={turn.id}>
              <article className="ask-v2-user-message">
                <span>You</span>
                <p>{turn.question}</p>
              </article>
              <AskV2AssistantTurn
                turn={turn}
                latest={index === conversation.turns.length - 1}
                onClarify={(entity) => conversation.clarify(turn, entity)}
                onFollowUp={conversation.submit}
                onRetry={() => conversation.retry(turn.id)}
              />
            </div>
          ))}
        </section>
      )}

      <div className="ask-v2-composer-dock">
        <AskComposer
          disabled={conversation.isPending}
          onSubmit={conversation.submit}
        />
        <p>
          Observational evidence is not proof of causation. Unsupported
          projections and counterfactuals remain explicitly unavailable.
        </p>
      </div>
    </section>
  );
}
