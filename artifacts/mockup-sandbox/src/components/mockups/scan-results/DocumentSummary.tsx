import { useMemo } from "react";
import "./_group.css";
import {
  ACTION_LABELS,
  CATEGORY_LABELS,
  formatChf,
  midpointValue,
} from "./types";
import { MOCK_REPORT } from "./mockReport";

/**
 * DocumentSummary — premium legal-opinion aesthetic.
 *
 * Hypothesis: Luis wants something that looks and reads like the Rechtsgutachten
 * a cantonal lawyer would email him: numbered sections, footnoted citations,
 * Source Serif body text, strict typographic discipline. The screen is meant
 * to be printed, forwarded, archived. It mirrors the tone of the
 * DocumentIntake wizard variant.
 */

interface NumberedFootnote {
  id: string;
  number: number;
  benefitId: string;
  citation: { sr_number: string; article: string; paragraph?: string | null; quote_under_15_words: string };
}

export default function DocumentSummary() {
  const sorted = useMemo(
    () => [...MOCK_REPORT.benefits].sort((a, b) => b.confidence - a.confidence),
    [],
  );

  // Build a flat numbered footnote list across all benefits in order.
  const footnotes: NumberedFootnote[] = useMemo(() => {
    const fns: NumberedFootnote[] = [];
    let n = 1;
    for (const b of sorted) {
      for (const c of b.citations) {
        fns.push({
          id: `${b.entitlement_id}-${n}`,
          number: n++,
          benefitId: b.entitlement_id,
          citation: c,
        });
      }
    }
    return fns;
  }, [sorted]);

  const footnoteByBenefit = useMemo(() => {
    const map = new Map<string, NumberedFootnote[]>();
    for (const f of footnotes) {
      const arr = map.get(f.benefitId) ?? [];
      arr.push(f);
      map.set(f.benefitId, arr);
    }
    return map;
  }, [footnotes]);

  const totalLow = sorted.reduce((a, b) => a + b.estimated_value_chf.min, 0);
  const totalHigh = sorted.reduce((a, b) => a + b.estimated_value_chf.max, 0);

  const generatedDate = new Date(MOCK_REPORT.generated_at).toLocaleDateString(
    "en-CH",
    { day: "numeric", month: "long", year: "numeric" },
  );

  return (
    <div className="slaw-results slaw-results--doc min-h-screen bg-[#f4f1ea]">
      {/* Page */}
      <div className="mx-auto max-w-2xl bg-[#fbf9f3] px-12 pt-16 pb-20 shadow-[0_2px_30px_-10px_rgba(15,23,42,0.18)] my-8 border border-[#e7e2d4]">
        {/* Letterhead */}
        <header className="border-b-2 border-[#1f2937]/80 pb-6">
          <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.22em] text-[#6b6757]">
            <span>Slaw · Cabinet juridique numérique</span>
            <span>Réf. {MOCK_REPORT.profile_hash.slice(0, 8).toUpperCase()}</span>
          </div>
          <h1 className="mt-7 font-serif text-[34px] leading-[1.15] tracking-tight text-[#1a1a1a]">
            Rapport d’analyse des droits
          </h1>
          <p className="mt-2 text-[13px] italic text-[#6b6757]">
            Analyse des entitlements applicables sous le droit suisse fédéral et
            cantonal — établi le {generatedDate}.
          </p>
        </header>

        {/* I. Synopsis */}
        <section className="mt-9">
          <SectionHeading numeral="I." title="Synopsis" />
          <p className="mt-3 text-[15px] leading-[1.75] text-[#262626]">
            Au terme de l’analyse, <strong>{sorted.length}</strong> droits,
            déductions et protections ont été identifiés comme applicables au
            profil examiné, pour une valeur estimée cumulée de{" "}
            <strong className="whitespace-nowrap">
              CHF {formatChf(totalLow)} à CHF {formatChf(totalHigh)}
            </strong>
            . {MOCK_REPORT.suppressed_count} entitlement(s) supplémentaire(s) ont
            été écartés faute d’une confiance suffisante et sont conservés
            au dossier.
          </p>

          <div className="mt-5 grid grid-cols-3 gap-px overflow-hidden rounded border border-[#d8d2bf] bg-[#d8d2bf] text-[12px]">
            <SynopsisCell label="Entitlements retenus" value={String(sorted.length)} />
            <SynopsisCell
              label="Valeur médiane"
              value={`CHF ${formatChf(
                sorted.reduce((a, b) => a + midpointValue(b.estimated_value_chf), 0),
              )}`}
            />
            <SynopsisCell
              label="Confiance moyenne"
              value={`${Math.round(
                (sorted.reduce((a, b) => a + b.confidence, 0) / sorted.length) * 100,
              )}%`}
            />
          </div>
        </section>

        {/* II. Analyse */}
        <section className="mt-10">
          <SectionHeading numeral="II." title="Analyse détaillée" />

          <ol className="mt-4 space-y-7">
            {sorted.map((b, i) => {
              const fns = footnoteByBenefit.get(b.entitlement_id) ?? [];
              return (
                <li key={b.entitlement_id} className="text-[15px] leading-[1.75] text-[#262626]">
                  <h3 className="font-serif text-[17px] font-semibold tracking-tight text-[#1a1a1a]">
                    <span className="mr-1.5 tabular-nums text-[#6b6757]">
                      §{i + 1}.
                    </span>
                    {b.title}
                  </h3>
                  <div className="mt-1 text-[11.5px] uppercase tracking-[0.14em] text-[#6b6757]">
                    {CATEGORY_LABELS[b.category]} ·{" "}
                    <span className="not-italic">
                      Valeur estimée CHF {formatChf(b.estimated_value_chf.min)}–
                      {formatChf(b.estimated_value_chf.max)} /{" "}
                      {b.estimated_value_chf.per === "year"
                        ? "an"
                        : b.estimated_value_chf.per === "month"
                          ? "mois"
                          : "unique"}
                    </span>{" "}
                    · Confiance {Math.round(b.confidence * 100)}%
                  </div>

                  <p className="mt-3">
                    {b.llm_reasoning}
                    {fns.map((fn) => (
                      <FootnoteRef key={fn.id} number={fn.number} />
                    ))}
                  </p>

                  {b.evidence.length > 0 && (
                    <div className="mt-3 border-l-2 border-[#d8d2bf] pl-4 text-[13px] italic text-[#5a564a]">
                      <span className="not-italic font-semibold uppercase tracking-[0.12em] text-[10.5px] text-[#6b6757]">
                        Éléments retenus.{" "}
                      </span>
                      {b.evidence.map((e, ei) => (
                        <span key={ei}>
                          {ei > 0 && "; "}
                          <span className="not-italic text-[#1a1a1a]">{e.field}</span>{" "}
                          = {String(e.value)}
                        </span>
                      ))}
                      .
                    </div>
                  )}

                  <div className="mt-3 text-[12px] text-[#6b6757]">
                    <span className="font-semibold uppercase tracking-[0.12em] text-[10.5px]">
                      Suite à donner —
                    </span>{" "}
                    {ACTION_LABELS[b.required_action]}
                    {b.time_limit_days != null && (
                      <>
                        {" "}
                        <span className="text-[#a14b1f]">
                          (délai de {b.time_limit_days} jour
                          {b.time_limit_days > 1 ? "s" : ""})
                        </span>
                      </>
                    )}
                    .
                  </div>
                </li>
              );
            })}
          </ol>
        </section>

        {/* III. Sources */}
        <section className="mt-12">
          <SectionHeading numeral="III." title="Sources et fondements légaux" />
          <ol className="mt-4 space-y-2 text-[12.5px] leading-[1.75] text-[#262626]">
            {footnotes.map((fn) => (
              <li key={fn.id} className="flex gap-2">
                <span className="flex-none font-semibold tabular-nums text-[#6b6757]">
                  {fn.number}.
                </span>
                <span>
                  <span className="font-semibold">SR {fn.citation.sr_number}</span> Art.{" "}
                  {fn.citation.article}
                  {fn.citation.paragraph && ` al. ${fn.citation.paragraph}`} —{" "}
                  <span className="italic">“{fn.citation.quote_under_15_words}”</span>
                </span>
              </li>
            ))}
          </ol>
        </section>

        {/* Footer */}
        <footer className="mt-12 border-t border-[#d8d2bf] pt-5 text-[11.5px] italic leading-relaxed text-[#6b6757]">
          Le présent rapport ne se substitue pas à l’avis d’un avocat inscrit au
          barreau cantonal. Les valeurs estimées sont indicatives et doivent
          être recoupées avec votre situation individuelle. Document généré
          automatiquement par Slaw, profil de référence{" "}
          <span className="not-italic font-semibold">
            {MOCK_REPORT.profile_hash}
          </span>
          .
        </footer>
      </div>
    </div>
  );
}

function SectionHeading({ numeral, title }: { numeral: string; title: string }) {
  return (
    <h2 className="flex items-baseline gap-3 border-b border-[#d8d2bf] pb-2 font-serif text-[19px] font-semibold tracking-tight text-[#1a1a1a]">
      <span className="text-[#6b6757]">{numeral}</span>
      <span>{title}</span>
    </h2>
  );
}

function SynopsisCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-[#fbf9f3] px-4 py-3">
      <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#6b6757]">
        {label}
      </div>
      <div className="mt-0.5 font-serif text-[18px] tabular-nums text-[#1a1a1a]">
        {value}
      </div>
    </div>
  );
}

function FootnoteRef({ number }: { number: number }) {
  return (
    <sup className="ml-0.5 font-sans text-[10.5px] font-semibold tabular-nums text-[#0b6b3a]">
      [{number}]
    </sup>
  );
}
