"use strict";

const VERSION_TIMEOUT_MS = 5000;
const SEARCH_TIMEOUT_MS = 15000;
const ASK_TIMEOUT_MS = 125000;
const FEEDBACK_TIMEOUT_MS = 8000;
const MIN_QUESTION_CHARS = 3;
const MAX_QUESTION_CHARS = 500;
const MIN_YEAR = 1990;
const MAX_YEAR = 2100;

const elements = {
  form: document.getElementById("ask-form"),
  question: document.getElementById("question"),
  count: document.getElementById("question-count"),
  regulator: document.getElementById("regulator"),
  yearFrom: document.getElementById("year-from"),
  yearTo: document.getElementById("year-to"),
  sourcesOnly: document.getElementById("sources-only"),
  submit: document.getElementById("submit"),
  error: document.getElementById("form-error"),
  loading: document.getElementById("loading"),
  loadingText: document.getElementById("loading-text"),
  result: document.getElementById("result"),
  answerCard: document.getElementById("answer-card"),
  answer: document.getElementById("answer"),
  feedback: document.getElementById("feedback"),
  feedbackLabel: document.getElementById("feedback-label"),
  sources: document.getElementById("sources"),
  sourcesTitle: document.getElementById("sources-title"),
  citations: document.getElementById("citations"),
  citationTemplate: document.getElementById("citation-template"),
};

let currentRequestId = null;

function showService(state, message) {
  document.getElementById("service-dot").dataset.state = state;
  document.getElementById("service-status").textContent = message;
}

async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, cache: "no-store", signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function loadVersion() {
  const promptVersion = document.getElementById("prompt-version");
  try {
    const response = await fetchWithTimeout("/version", {}, VERSION_TIMEOUT_MS);
    if (!response.ok) {
      throw new Error(`Unexpected status ${response.status}`);
    }
    const version = await response.json();
    promptVersion.textContent = version.prompt_version;
    showService("online", "Service online");
  } catch {
    promptVersion.textContent = "unavailable";
    showService("offline", "Service unavailable");
  }
}

function showError(message) {
  elements.error.textContent = message;
  elements.error.hidden = false;
}

function clearError() {
  elements.error.textContent = "";
  elements.error.hidden = true;
}

function parseYear(input) {
  const raw = input.value.trim();
  if (raw === "") {
    return { value: null, valid: input.validity.valid };
  }
  const year = Number(raw);
  return { value: year, valid: Number.isInteger(year) && year >= MIN_YEAR && year <= MAX_YEAR };
}

function buildRequest() {
  const question = elements.question.value.trim();
  if (question.length < MIN_QUESTION_CHARS) {
    return { error: `Enter a question of at least ${MIN_QUESTION_CHARS} characters.` };
  }
  if (question.length > MAX_QUESTION_CHARS) {
    return { error: `Keep your question under ${MAX_QUESTION_CHARS} characters.` };
  }

  const yearFrom = parseYear(elements.yearFrom);
  const yearTo = parseYear(elements.yearTo);
  if (!yearFrom.valid || !yearTo.valid) {
    return { error: `Years must be between ${MIN_YEAR} and ${MAX_YEAR}.` };
  }
  if (yearFrom.value !== null && yearTo.value !== null && yearFrom.value > yearTo.value) {
    return { error: "From year cannot be after To year." };
  }

  const filters = {};
  if (elements.regulator.value) {
    filters.regulator = elements.regulator.value;
  }
  if (yearFrom.value !== null) {
    filters.year_from = yearFrom.value;
  }
  if (yearTo.value !== null) {
    filters.year_to = yearTo.value;
  }

  const body = { question };
  if (Object.keys(filters).length > 0) {
    body.filters = filters;
  }
  return { body };
}

function setBusy(busy, sourcesOnly) {
  elements.submit.disabled = busy;
  elements.loading.hidden = !busy;
  elements.loadingText.textContent = sourcesOnly
    ? "Searching the circulars…"
    : "Reading the circulars and writing an answer. This can take a few seconds…";
}

function renderAnswerText(text) {
  elements.answer.replaceChildren();
  for (const part of text.split(/(\[\d+\])/)) {
    const match = part.match(/^\[(\d+)\]$/);
    if (match && document.getElementById(`source-${match[1]}`)) {
      const link = document.createElement("a");
      link.className = "citation-ref";
      link.href = `#source-${match[1]}`;
      link.textContent = part;
      link.setAttribute("aria-label", `Source ${match[1]}`);
      elements.answer.append(link);
    } else {
      elements.answer.append(document.createTextNode(part));
    }
  }
}

function safeSourceUrl(rawUrl, page) {
  try {
    const url = new URL(rawUrl);
    if (url.protocol !== "https:") {
      return null;
    }
    url.hash = `page=${page}`;
    return url.href;
  } catch {
    return null;
  }
}

function formatDate(isoDate) {
  const parsed = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return isoDate;
  }
  return parsed.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

function renderCitations(citations, title) {
  elements.citations.replaceChildren();
  for (const citation of citations) {
    const fragment = elements.citationTemplate.content.cloneNode(true);
    const item = fragment.querySelector(".citation");
    const set = (selector, value) => {
      fragment.querySelector(selector).textContent = value;
    };

    item.id = `source-${citation.n}`;
    set(".citation-number", `[${citation.n}]`);
    set(".citation-regulator", citation.regulator);
    set(".citation-date", formatDate(citation.issued_date));
    set(".citation-page", `Page ${citation.page}`);
    set(".citation-title", citation.title);
    set(".citation-snippet", citation.snippet);

    const circular = fragment.querySelector(".citation-circular");
    if (citation.circular_no) {
      circular.textContent = citation.circular_no;
    } else {
      circular.remove();
    }

    const link = fragment.querySelector(".citation-link");
    const href = safeSourceUrl(citation.source_url, citation.page);
    if (href) {
      link.href = href;
      link.setAttribute("aria-label", `Open official PDF for ${citation.title}, page ${citation.page}`);
    } else {
      link.remove();
    }
    elements.citations.append(fragment);
  }
  elements.sourcesTitle.textContent = title;
  elements.sources.hidden = citations.length === 0;
}

function resetFeedback() {
  elements.feedbackLabel.textContent = "Was this helpful?";
  for (const button of elements.feedback.querySelectorAll("button")) {
    button.disabled = false;
    button.hidden = false;
  }
}

function clearResult() {
  currentRequestId = null;
  elements.result.hidden = true;
  elements.answerCard.hidden = true;
  elements.answerCard.classList.remove("refused");
  elements.answer.replaceChildren();
  elements.citations.replaceChildren();
  elements.sources.hidden = true;
}

function showResult() {
  elements.result.hidden = false;
  elements.result.scrollIntoView({ block: "start" });
}

function renderAsk(data) {
  currentRequestId = data.request_id;
  renderCitations(data.citations, "Sources");
  renderAnswerText(data.answer);
  elements.answerCard.classList.toggle("refused", data.refused);
  elements.answerCard.hidden = false;
  resetFeedback();
  showResult();
}

function renderSearch(data) {
  renderCitations(data.hits, "Matching sources");
  if (data.hits.length === 0) {
    showError("No matching passages were found. Try different words or fewer filters.");
    return;
  }
  showResult();
}

function messageForFailure(response, data) {
  if (response.status === 422) {
    return "Please check your question and filters.";
  }
  if (data && data.error === "llm_unavailable") {
    return "The answer service is unavailable right now. Turn on Sources only to search the circulars.";
  }
  if (data && data.error === "vector_db_unavailable") {
    return "The circular index is unavailable right now. Please try again shortly.";
  }
  return "Something went wrong. Please try again.";
}

async function submitQuestion(event) {
  event.preventDefault();
  if (elements.submit.disabled) {
    return;
  }
  clearError();

  const request = buildRequest();
  if (request.error) {
    showError(request.error);
    return;
  }

  const sourcesOnly = elements.sourcesOnly.checked;
  clearResult();
  setBusy(true, sourcesOnly);
  try {
    const response = await fetchWithTimeout(
      sourcesOnly ? "/api/v1/search" : "/api/v1/ask",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request.body),
      },
      sourcesOnly ? SEARCH_TIMEOUT_MS : ASK_TIMEOUT_MS,
    );
    const data = await response.json().catch(() => null);
    if (!response.ok || !data) {
      showError(messageForFailure(response, data));
      return;
    }
    if (sourcesOnly) {
      renderSearch(data);
    } else {
      renderAsk(data);
    }
  } catch (error) {
    showError(
      error.name === "AbortError"
        ? "That took too long. Please try again, or turn on Sources only."
        : "Could not reach Niyam. Check your connection and try again.",
    );
  } finally {
    setBusy(false, sourcesOnly);
  }
}

async function sendFeedback(button) {
  if (!currentRequestId) {
    return;
  }
  const buttons = elements.feedback.querySelectorAll("button");
  buttons.forEach((item) => {
    item.disabled = true;
  });
  try {
    const response = await fetchWithTimeout(
      "/api/v1/feedback",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: currentRequestId, rating: button.dataset.rating }),
      },
      FEEDBACK_TIMEOUT_MS,
    );
    if (!response.ok) {
      throw new Error(`Unexpected status ${response.status}`);
    }
    elements.feedbackLabel.textContent = "Thanks for your feedback.";
    buttons.forEach((item) => {
      item.hidden = true;
    });
  } catch {
    elements.feedbackLabel.textContent = "Could not save feedback. Try again.";
    buttons.forEach((item) => {
      item.disabled = false;
    });
  }
}

function updateCount() {
  elements.count.textContent = `${elements.question.value.length} / ${MAX_QUESTION_CHARS}`;
}

elements.form.addEventListener("submit", submitQuestion);
elements.question.addEventListener("input", updateCount);
elements.question.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    elements.form.requestSubmit();
  }
});
elements.sourcesOnly.addEventListener("change", () => {
  elements.submit.textContent = elements.sourcesOnly.checked ? "Search" : "Ask";
});
elements.feedback.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-rating]");
  if (button) {
    sendFeedback(button);
  }
});

updateCount();
loadVersion();
