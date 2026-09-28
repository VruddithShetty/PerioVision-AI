import { ClipboardList, Cigarette, Droplets, HeartHandshake, LineChart, Pencil, Plus, ScanLine, Search, Stethoscope, UserRound } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "@/api/client";
import { usePatient, usePatients, useSavePatient } from "@/api/hooks";
import type { Patient } from "@/api/types";
import { Drawer, EmptyState, ErrorState, LoadingRows, PageHeader, Table } from "@/components/ui/blocks";
import { Badge, Button, Field, Input, Select } from "@/components/ui/primitives";
import { useDebounced } from "@/hooks";
import { fmtDate, REVIEW_LABEL, REVIEW_TONE, stageColor } from "@/lib/format";
import { useCan } from "@/store/auth";

type FormState = {
  name: string;
  age: string;
  sex: string;
  contact: string;
  notes: string;
  smoking_status: string;
  cigarettes_per_day: string;
  diabetic: string;
  hba1c: string;
  teeth_lost_perio: string;
};

const EMPTY: FormState = {
  name: "", age: "", sex: "unknown", contact: "", notes: "", smoking_status: "unknown",
  cigarettes_per_day: "", diabetic: "unknown", hba1c: "", teeth_lost_perio: "",
};

function toForm(p?: Patient): FormState {
  if (!p) return EMPTY;
  return {
    name: p.patient_name ?? "",
    age: p.age?.toString() ?? "",
    sex: p.sex ?? "unknown",
    contact: p.contact_number ?? "",
    notes: p.notes ?? "",
    smoking_status: p.smoking_status ?? "unknown",
    cigarettes_per_day: p.cigarettes_per_day?.toString() ?? "",
    diabetic: p.diabetic === true ? "yes" : p.diabetic === false ? "no" : "unknown",
    hba1c: p.hba1c?.toString() ?? "",
    teeth_lost_perio: p.teeth_lost_perio?.toString() ?? "",
  };
}

function PatientForm({ patient, onDone }: { patient?: Patient; onDone: (p: Patient) => void }) {
  const [f, setF] = useState<FormState>(toForm(patient));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const save = useSavePatient();
  const set = (k: keyof FormState) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErrors({});
    const num = (v: string) => (v === "" ? null : Number(v));
    const body: Record<string, unknown> = {
      name: f.name,
      age: num(f.age),
      sex: f.sex,
      contact: f.contact || null,
      notes: f.notes || null,
      smoking_status: f.smoking_status,
      cigarettes_per_day: f.smoking_status === "current" ? num(f.cigarettes_per_day) : null,
      diabetic: f.diabetic === "unknown" ? null : f.diabetic === "yes",
      hba1c: num(f.hba1c),
      teeth_lost_perio: num(f.teeth_lost_perio),
    };
    try {
      onDone(await save.mutateAsync({ id: patient?.patient_id, body }));
    } catch (err) {
      const d = (err as ApiError).details as { field: string; message: string }[] | undefined;
      if (Array.isArray(d)) setErrors(Object.fromEntries(d.map((x) => [x.field, x.message])));
      else setErrors({ _: (err as Error).message });
    }
  };

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label="Full name" htmlFor="name" error={errors.name}>
            <Input id="name" required value={f.name} onChange={set("name")} />
          </Field>
        </div>
        <Field label="Age" htmlFor="age" error={errors.age}>
          <Input id="age" type="number" min={0} max={120} value={f.age} onChange={set("age")} />
        </Field>
        <Field label="Sex" htmlFor="sex">
          <Select id="sex" value={f.sex} onChange={set("sex")}>
            <option value="unknown">Not recorded</option>
            <option value="female">Female</option>
            <option value="male">Male</option>
            <option value="other">Other</option>
          </Select>
        </Field>
        <Field label="Contact" htmlFor="contact" hint="Encrypted at rest">
          <Input id="contact" value={f.contact} onChange={set("contact")} />
        </Field>
        <Field label="Teeth lost to periodontitis" htmlFor="tl" hint="Needed for Stage IV">
          <Input id="tl" type="number" min={0} max={32} value={f.teeth_lost_perio} onChange={set("teeth_lost_perio")} />
        </Field>
      </div>
      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
        <p className="label mb-3">Risk factors (used for grade modifiers and risk fusion)</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Smoking" htmlFor="smoking">
            <Select id="smoking" value={f.smoking_status} onChange={set("smoking_status")}>
              <option value="unknown">Unknown</option>
              <option value="never">Never</option>
              <option value="former">Former</option>
              <option value="current">Current</option>
            </Select>
          </Field>
          <Field label="Cigarettes per day" htmlFor="cpd" error={errors.cigarettes_per_day}>
            <Input id="cpd" type="number" min={0} max={100} disabled={f.smoking_status !== "current"} value={f.cigarettes_per_day} onChange={set("cigarettes_per_day")} />
          </Field>
          <Field label="Diabetes" htmlFor="dm">
            <Select id="dm" value={f.diabetic} onChange={set("diabetic")}>
              <option value="unknown">Unknown</option>
              <option value="no">No</option>
              <option value="yes">Yes</option>
            </Select>
          </Field>
          <Field label="HbA1c (%)" htmlFor="hba1c" error={errors.hba1c}>
            <Input id="hba1c" type="number" step="0.1" min={3} max={20} value={f.hba1c} onChange={set("hba1c")} />
          </Field>
        </div>
      </div>
      <Field label="Clinical notes" htmlFor="notes" hint="Encrypted at rest">
        <textarea id="notes" rows={3} className="input" value={f.notes} onChange={set("notes")} />
      </Field>
      {errors._ && <p className="text-sm text-critical-400">{errors._}</p>}
      <Button type="submit" loading={save.isPending} className="w-full">
        {patient ? "Save changes" : "Create patient"}
      </Button>
    </form>
  );
}

function PatientDetail({ id, onEdit }: { id: number; onEdit: () => void }) {
  const { data: p, isLoading, error } = usePatient(id);
  const canWrite = useCan("patient:write");
  const canRun = useCan("analysis:run");
  if (isLoading) return <LoadingRows rows={6} />;
  if (error || !p) return <ErrorState error={error} />;
  return (
    <div className="space-y-6">
      <div className="flex items-start gap-4">
        <div className="rounded-2xl bg-gradient-to-br from-brand-400/20 to-teal-400/10 p-3 text-brand-300">
          <UserRound className="h-7 w-7" />
        </div>
        <div className="flex-1">
          <p className="font-display text-xl font-semibold">{p.patient_name}</p>
          <p className="font-mono text-xs text-brand-300">{p.pseudo_id} · #{p.patient_id}</p>
        </div>
        {canWrite && (
          <Button variant="outline" size="sm" icon={<Pencil className="h-3.5 w-3.5" />} onClick={onEdit}>
            Edit
          </Button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        {[
          ["Age", p.age ?? "–"],
          ["Sex", p.sex ?? "–"],
          ["Smoking", p.smoking_status === "current" ? `Current · ${p.cigarettes_per_day ?? "?"}/day` : p.smoking_status ?? "–"],
          ["Diabetes", p.diabetic == null ? "Unknown" : p.diabetic ? `Yes · HbA1c ${p.hba1c ?? "?"}%` : "No"],
        ].map(([k, v]) => (
          <div key={k as string} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
            <p className="label">{k}</p>
            <p className="mt-1 capitalize text-mist-100">{v}</p>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        {canRun && (
          <Link to={`/app/analysis/new?patient=${p.patient_id}`}>
            <Button size="sm" icon={<ScanLine className="h-3.5 w-3.5" />}>New analysis</Button>
          </Link>
        )}
        <Link to={`/app/patients/${p.patient_id}/progression`}>
          <Button size="sm" variant="outline" icon={<LineChart className="h-3.5 w-3.5" />}>Progression</Button>
        </Link>
        <Link to={`/app/patients/${p.patient_id}/perio-chart`}>
          <Button size="sm" variant="outline" icon={<Stethoscope className="h-3.5 w-3.5" />}>Perio chart</Button>
        </Link>
        <Link to={`/app/patients/${p.patient_id}/care-plan`}>
          <Button size="sm" variant="outline" icon={<ClipboardList className="h-3.5 w-3.5" />}>Care plan</Button>
        </Link>
        <Link to={`/app/patients/${p.patient_id}/explain`}>
          <Button size="sm" variant="subtle" icon={<HeartHandshake className="h-3.5 w-3.5" />}>Explain to patient</Button>
        </Link>
      </div>
      <div>
        <p className="label mb-3">Visits</p>
        {!p.analyses?.length ? (
          <EmptyState title="No radiographs analysed yet" />
        ) : (
          <ol className="relative space-y-3 border-l border-white/10 pl-5">
            {[...p.analyses].reverse().map((a) => (
              <li key={a.analysis_id} className="relative">
                <span className="absolute -left-[27px] top-3 h-3 w-3 rounded-full border-2 border-ink-900" style={{ background: stageColor(a.stage) }} />
                <Link to={`/app/analysis/${a.analysis_id}`} className="glass block p-3 transition hover:border-brand-400/30">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">{fmtDate(a.visit_date)}</p>
                    <Badge tone={REVIEW_TONE[a.review_status]}>{REVIEW_LABEL[a.review_status]}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-mist-400">
                    Stage {a.stage ?? "–"} · risk <span className="capitalize">{a.risk ?? "–"}</span> {a.mode === "demo" && "· demo"}
                  </p>
                </Link>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

export default function PatientsPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const debounced = useDebounced(q);
  const { data, isLoading, error, refetch } = usePatients(debounced);
  const canWrite = useCan("patient:write");
  const openId = params.get("id") ? Number(params.get("id")) : null;
  const [mode, setMode] = useState<"view" | "edit" | "new" | null>(null);

  useEffect(() => {
    if (openId && !mode) setMode("view");
  }, [openId, mode]);

  const close = () => {
    setMode(null);
    params.delete("id");
    setParams(params);
  };
  const open = (id: number) => {
    params.set("id", String(id));
    setParams(params);
    setMode("view");
  };

  return (
    <div>
      <PageHeader
        eyebrow="Patients"
        title="Patient registry"
        subtitle="Names and contacts are AES-256-GCM encrypted. Search matches exact names or pseudonymous IDs through a keyed blind index."
        actions={canWrite && <Button icon={<Plus className="h-4 w-4" />} onClick={() => setMode("new")}>New patient</Button>}
      />
      <div className="relative mb-4 max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-mist-500" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Exact name or pseudonym (P-…)" className="pl-10" aria-label="Search patients" />
      </div>
      {error ? (
        <ErrorState error={error} retry={refetch} />
      ) : isLoading ? (
        <LoadingRows />
      ) : !data?.length ? (
        <EmptyState
          title={q ? "No exact match" : "No patients yet"}
          body={q ? "Search uses an exact-match blind index so names are never stored in plain text." : "Create the first patient to start analysing radiographs."}
          action={canWrite && !q && <Button onClick={() => setMode("new")} icon={<Plus className="h-4 w-4" />}>New patient</Button>}
        />
      ) : (
        <Table head={["Patient", "Pseudonym", "Age", "Risk factors", "Registered"]}>
          {data.map((p) => (
            <tr key={p.patient_id} className="cursor-pointer transition hover:bg-white/[0.03]" onClick={() => open(p.patient_id)}>
              <td className="px-4 py-3 font-medium text-mist-100">{p.patient_name}</td>
              <td className="px-4 py-3 font-mono text-xs text-brand-300">{p.pseudo_id}</td>
              <td className="px-4 py-3 text-mist-300">{p.age ?? "–"}</td>
              <td className="px-4 py-3">
                <div className="flex gap-1.5">
                  {p.smoking_status === "current" && <Badge tone="review"><Cigarette className="h-3 w-3" /> smoker</Badge>}
                  {p.diabetic && <Badge tone="review"><Droplets className="h-3 w-3" /> diabetes</Badge>}
                  {p.smoking_status !== "current" && !p.diabetic && <span className="text-xs text-mist-500">none recorded</span>}
                </div>
              </td>
              <td className="px-4 py-3 text-mist-400">{fmtDate(p.created_date)}</td>
            </tr>
          ))}
        </Table>
      )}

      <Drawer open={mode !== null} onClose={close} title={mode === "new" ? "New patient" : mode === "edit" ? "Edit patient" : "Patient"}>
        {mode === "new" && <PatientForm onDone={(p) => open(p.patient_id)} />}
        {mode === "view" && openId && <PatientDetail id={openId} onEdit={() => setMode("edit")} />}
        {mode === "edit" && openId && <EditWrapper id={openId} onDone={() => setMode("view")} />}
      </Drawer>
    </div>
  );
}

function EditWrapper({ id, onDone }: { id: number; onDone: () => void }) {
  const { data } = usePatient(id);
  if (!data) return <LoadingRows />;
  return <PatientForm patient={data} onDone={onDone} />;
}
