import "@fontsource-variable/bricolage-grotesque";
import "../landing.css";
import { Link } from "react-router";
import { Credits } from "../components/Credits";
import { Disclosure } from "../components/Disclosure";

/*
 * Public landing page (Hallmark redesign, shape 05 Workbench). Every picture is a real screen of
 * the app, captured from a local sample student; the page's styles live in landing.css and are
 * scoped to .landing so no app screen changes. Headline and button words are the brief's own.
 */

const STAGES = [
  {
    title: "Take a short check",
    text: "About ten questions show what you already know.",
    img: "/landing/check.png",
    width: 1212,
    height: 1224,
    shot: "shot-check",
    alt: "A placement question about bank transactions, with seven options to select.",
  },
  {
    title: "Get one clear next step",
    text: "Every day, one thing to do, and why it helps you.",
    img: "/landing/today.png",
    width: 1824,
    height: 430,
    shot: "shot-today",
    alt: "The Today card naming one skill, how many more correct answers it needs, and a Start button.",
  },
  {
    title: "Practise and improve",
    text: "Questions adapt to you, and fresh checks show real progress.",
    img: "/landing/improving.png",
    width: 1212,
    height: 732,
    shot: "shot-improving",
    alt: "A correct answer with the message: You're improving! Two in a row, so the next question is a little harder.",
  },
];

const PROMISES = [
  { title: "Adapts to you", text: "Two right in a row and it gets harder; two wrong and it eases off." },
  { title: "Honest progress", text: "Your status comes from your own answers, never from a guess." },
  { title: "Help when stuck", text: "Hints, worked examples and an AI tutor that explains mistakes." },
];

function Wordmark() {
  return (
    <Link to="/" className="lp-wordmark" aria-label="MENTORX home">
      <span className="lp-wordmark-badge" aria-hidden>
        M
      </span>
      <span aria-hidden>
        MENTOR<span className="lp-wordmark-x">X</span>
      </span>
    </Link>
  );
}

export function LandingPage() {
  return (
    <div className="landing" data-theme="landing">
      <header className="lp-container lp-nav">
        <Wordmark />
        <nav className="lp-nav-links" aria-label="Account">
          <a href="#how" className="lp-nav-link lp-nav-link-optional">
            How it works
          </a>
          <Link to="/login" className="lp-nav-link">
            Sign in
          </Link>
          <Link to="/register" className="lp-button lp-button-quiet">
            Get started
          </Link>
        </nav>
      </header>

      <main>
        <section className="lp-hero" aria-labelledby="lp-title">
          <div className="lp-container lp-hero-grid">
            <div>
              <h1 id="lp-title">
                Your Learning Journey.{" "}
                <br />
                Your Pace.{" "}
                <br />
                Your Mentor.
              </h1>
              <p className="lead">A calm, adaptive tutor that finds what you know and shows you the next step.</p>
              <div className="lp-actions">
                <Link to="/register" className="lp-button lp-button-primary">
                  Get started free
                </Link>
                <Link to="/login" className="lp-button lp-button-quiet">
                  Sign in
                </Link>
              </div>
              <p className="lp-terms">Free to start. Maths for grades 4 to 8, and Geography map skills.</p>
            </div>
            <figure>
              <div className="lp-shot" data-slot="hero" data-kind="product" data-alt="The learning profile after the placement check">
                <img
                  src="/landing/skills.png"
                  width={1800}
                  height={1384}
                  fetchPriority="high"
                  alt="A student's skills after the placement check: Division of Fractions marked Needs practice at 0 of 5 correct, eight others Getting there, each with its own count of correct answers."
                />
              </div>
              <figcaption className="lp-caption">A sample student after the check. Each label comes from their own answers.</figcaption>
            </figure>
          </div>
        </section>

        <section id="how" className="lp-how" aria-labelledby="lp-how-title">
          <div className="lp-container">
            <h2 id="lp-how-title">Ten questions, then your next step</h2>
            <ol className="lp-stages">
              {STAGES.map((s) => (
                <li key={s.title} className="lp-stage">
                  <div className="lp-stage-text">
                    <h3>{s.title}</h3>
                    <p>{s.text}</p>
                  </div>
                  <div className={`lp-shot ${s.shot}`} data-slot={s.shot} data-kind="product" data-alt={s.title}>
                    <img src={s.img} width={s.width} height={s.height} loading="lazy" alt={s.alt} />
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="lp-why" aria-labelledby="lp-why-title">
          <div className="lp-container lp-why-grid">
            <h2 id="lp-why-title">It follows your answers, not guesses</h2>
            <dl className="lp-rows">
              {PROMISES.map((p) => (
                <div key={p.title}>
                  <dt>{p.title}</dt>
                  <dd>{p.text}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section className="lp-close" aria-labelledby="lp-close-title">
          <div className="lp-container lp-close-grid">
            <div>
              <h2 id="lp-close-title">Start with ten questions.</h2>
              <div className="lp-actions">
                <Link to="/register" className="lp-button lp-button-primary">
                  Create your account
                </Link>
              </div>
            </div>
            <figure>
              <div className="lp-shot" data-slot="ai-tutor" data-kind="product" data-alt="The AI tutor explaining one mistake">
                <img
                  src="/landing/ai-tutor.png"
                  width={1224}
                  height={1108}
                  loading="lazy"
                  alt="An ordering question answered with two numbers swapped, the correct order, and the AI tutor's step-by-step explanation with a tip."
                />
              </div>
              <figcaption className="lp-caption">The AI tutor explaining one slip, step by step. Its words are labelled as AI-generated.</figcaption>
            </figure>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-container">
          <p className="lp-mast" aria-hidden>
            MENTORX
          </p>
          <div className="lp-footer-row">
            <div className="lp-footer-credits">
              <Disclosure variant="plain" title="Data & credits">
                <Credits showStatic />
              </Disclosure>
            </div>
            <Link to="/login" className="lp-nav-link">
              Sign in
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
