import { useRef, useState, type KeyboardEvent } from "react";
import { Send } from "lucide-react";

interface AskComposerProps {
  disabled: boolean;
  onSubmit: (question: string) => void;
}

export function AskComposer({ disabled, onSubmit }: AskComposerProps) {
  const [question, setQuestion] = useState("");
  const textarea = useRef<HTMLTextAreaElement>(null);
  const normalized = question.trim();
  const valid = normalized.length >= 3 && normalized.length <= 1_000;

  function submit() {
    if (disabled || !valid) return;
    onSubmit(normalized);
    setQuestion("");
    textarea.current?.focus();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form
      className="ask-v2-composer"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <label htmlFor="ask-v2-question">Ask a football question</label>
      <div className="ask-v2-composer-row">
        <textarea
          ref={textarea}
          id="ask-v2-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={handleKeyDown}
          minLength={3}
          maxLength={1000}
          rows={3}
          placeholder="Ask about a quarterback, coach, historical scheme, or projection…"
          disabled={disabled}
        />
        <button
          className="button button-primary"
          type="submit"
          disabled={disabled || !valid}
        >
          <Send aria-hidden="true" /> Ask
        </button>
      </div>
      <div className="ask-v2-composer-meta">
        <span>Ctrl/⌘ + Enter to submit · Enter for a new line</span>
        <span className={question.length > 900 ? "is-near-limit" : undefined}>
          {question.length}/1,000
        </span>
      </div>
    </form>
  );
}
