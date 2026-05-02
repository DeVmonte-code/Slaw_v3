import "./_group.css";

const CANTONS = [
  "AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR", "JU", "LU",
  "NE", "NW", "OW", "SG", "SH", "SO", "SZ", "TG", "TI", "UR", "VD", "VS", "ZG", "ZH",
];

const EMPLOYMENT_OPTIONS = [
  { value: "employee_full_time", label: "Employee (full-time)" },
  { value: "employee_part_time", label: "Employee (part-time)" },
  { value: "self_employed", label: "Self-employed" },
  { value: "business_owner", label: "Business owner" },
  { value: "unemployed", label: "Unemployed" },
  { value: "student", label: "Student" },
  { value: "retired", label: "Retired" },
];

const HOUSING_OPTIONS = [
  { value: "tenant", label: "Tenant" },
  { value: "owner", label: "Owner" },
  { value: "living_with_family", label: "Living with family" },
];

const MARITAL_OPTIONS = [
  { value: "single", label: "Single" },
  { value: "married", label: "Married" },
  { value: "registered_partnership", label: "Registered partnership" },
  { value: "divorced", label: "Divorced" },
  { value: "widowed", label: "Widowed" },
];

const INCOME_OPTIONS = [
  { value: "lt_30k", label: "Under CHF 30,000" },
  { value: "30_50k", label: "CHF 30,000–50,000" },
  { value: "50_80k", label: "CHF 50,000–80,000" },
  { value: "80_120k", label: "CHF 80,000–120,000" },
  { value: "120_200k", label: "CHF 120,000–200,000" },
  { value: "gt_200k", label: "Over CHF 200,000" },
];

export default function Current() {
  return (
    <div className="slaw-wizard min-h-screen bg-gray-50">
      <main className="mx-auto max-w-3xl p-8">
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-emerald-800">
            Swiss Legal Rights Scan
          </h1>
          <p className="mt-2 text-gray-600">
            Fill in your profile to discover rights, deductions, and protections
            available to you under Swiss law.
          </p>
        </header>

        <form className="space-y-6" onSubmit={(e) => e.preventDefault()}>
          <section className="rounded-lg border bg-white p-6 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-gray-800">
              Location &amp; Employment
            </h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Canton
                </label>
                <select
                  name="canton"
                  defaultValue="ZH"
                  className="mt-1 block w-full rounded border px-3 py-2"
                >
                  {CANTONS.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Employment Status
                </label>
                <select
                  name="employment_status"
                  defaultValue="employee_full_time"
                  className="mt-1 block w-full rounded border px-3 py-2"
                >
                  {EMPLOYMENT_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Employment Start Year
                </label>
                <input
                  name="employment_start_year"
                  type="number"
                  defaultValue={2018}
                  className="mt-1 block w-full rounded border px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Weekly Hours
                </label>
                <input
                  name="weekly_hours"
                  type="number"
                  defaultValue={42}
                  className="mt-1 block w-full rounded border px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Commute (km/day)
                </label>
                <input
                  name="commute_km_daily"
                  type="number"
                  defaultValue={12}
                  className="mt-1 block w-full rounded border px-3 py-2"
                />
              </div>
            </div>
          </section>

          <section className="rounded-lg border bg-white p-6 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-gray-800">Housing</h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Housing Status
                </label>
                <select
                  name="housing_status"
                  defaultValue="tenant"
                  className="mt-1 block w-full rounded border px-3 py-2"
                >
                  {HOUSING_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Rental Start Year
                </label>
                <input
                  name="rental_start_year"
                  type="number"
                  defaultValue={2018}
                  className="mt-1 block w-full rounded border px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Monthly Rent (CHF)
                </label>
                <input
                  name="rent_chf_monthly"
                  type="number"
                  defaultValue={2400}
                  className="mt-1 block w-full rounded border px-3 py-2"
                />
              </div>
              <div className="flex items-center gap-2 pt-6">
                <input
                  name="lease_reference_rate_tracked"
                  type="checkbox"
                  defaultChecked
                  id="rate_tracked"
                  className="h-4 w-4"
                />
                <label
                  htmlFor="rate_tracked"
                  className="text-sm font-medium text-gray-700"
                >
                  Reference rate tracked in lease
                </label>
              </div>
            </div>
          </section>

          <section className="rounded-lg border bg-white p-6 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-gray-800">
              Household &amp; Family
            </h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Marital Status
                </label>
                <select
                  name="marital_status"
                  defaultValue="married"
                  className="mt-1 block w-full rounded border px-3 py-2"
                >
                  {MARITAL_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Household Size
                </label>
                <input
                  name="household_size"
                  type="number"
                  min={1}
                  max={12}
                  defaultValue={4}
                  className="mt-1 block w-full rounded border px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Number of Children
                </label>
                <input
                  name="children_count"
                  type="number"
                  min={0}
                  max={10}
                  defaultValue={2}
                  className="mt-1 block w-full rounded border px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Childcare Cost (CHF/year)
                </label>
                <input
                  name="childcare_cost_chf_yearly"
                  type="number"
                  defaultValue={18000}
                  className="mt-1 block w-full rounded border px-3 py-2"
                />
              </div>
            </div>
          </section>

          <section className="rounded-lg border bg-white p-6 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-gray-800">
              Income &amp; Savings
            </h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Income Band (CHF/year)
                </label>
                <select
                  name="income_band_chf"
                  defaultValue="120_200k"
                  className="mt-1 block w-full rounded border px-3 py-2"
                >
                  {INCOME_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-center gap-2 pt-6">
                <input
                  name="has_third_pillar"
                  type="checkbox"
                  defaultChecked
                  id="pillar3"
                  className="h-4 w-4"
                />
                <label
                  htmlFor="pillar3"
                  className="text-sm font-medium text-gray-700"
                >
                  Has 3rd Pillar (Pillar 3a)
                </label>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  3rd Pillar Contributions This Year (CHF)
                </label>
                <input
                  name="third_pillar_chf_this_year"
                  type="number"
                  defaultValue={7056}
                  className="mt-1 block w-full rounded border px-3 py-2"
                />
              </div>
            </div>
          </section>

          <button
            type="submit"
            className="w-full rounded-lg bg-emerald-700 px-6 py-3 text-lg font-semibold text-white hover:bg-emerald-800"
          >
            Run Rights Scan
          </button>

          <p className="text-center text-xs text-gray-500">
            Not a substitute for advice from a Swiss attorney registered with a
            cantonal bar.
          </p>
        </form>
      </main>
    </div>
  );
}
