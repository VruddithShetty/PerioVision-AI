import { KeyRound, Lock, Plus, SlidersHorizontal, UserCog } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ApiError } from "@/api/client";
import { useAdminConfig, useLockUser, useSaveUser, useUsers } from "@/api/hooks";
import type { Role } from "@/api/types";
import { ErrorState, LoadingRows, Modal, PageHeader, Table, Tabs } from "@/components/ui/blocks";
import { Badge, Button, Card, CardTitle, Field, Input, Select } from "@/components/ui/primitives";
import { fmtDateTime } from "@/lib/format";
import { ROLE_LABEL, useAuth } from "@/store/auth";

function NewUserModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const save = useSaveUser();
  const [f, setF] = useState({ name: "", email: "", password: "", role: "dentist" as Role, clinic_name: "" });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    await save.mutateAsync({ body: { ...f, clinic_name: f.clinic_name || null } });
    onClose();
  };
  return (
    <Modal open={open} onClose={onClose} title="Create user">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Name" htmlFor="u-name"><Input id="u-name" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Email" htmlFor="u-email"><Input id="u-email" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Initial password" htmlFor="u-pw" hint="10+ characters with upper- and lower-case letters and a digit">
          <Input id="u-pw" type="password" required minLength={10} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Role" htmlFor="u-role">
            <Select id="u-role" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>
              {(Object.keys(ROLE_LABEL) as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </Select>
          </Field>
          <Field label="Clinic" htmlFor="u-clinic"><Input id="u-clinic" value={f.clinic_name} onChange={(e) => setF({ ...f, clinic_name: e.target.value })} /></Field>
        </div>
        {save.error && <p className="text-sm text-critical-400">{(save.error as ApiError).message}</p>}
        <Button type="submit" className="w-full" loading={save.isPending}>Create user</Button>
      </form>
    </Modal>
  );
}

function UsersPanel() {
  const { data, isLoading, error } = useUsers();
  const save = useSaveUser();
  const lock = useLockUser();
  const me = useAuth((s) => s.user?.doctor_id);
  const [creating, setCreating] = useState(false);
  if (error) return <ErrorState error={error} />;
  return (
    <Card>
      <CardTitle icon={<UserCog className="h-4 w-4" />} action={<Button size="sm" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setCreating(true)}>New user</Button>}>
        Users and roles
      </CardTitle>
      {isLoading ? <LoadingRows /> : (
        <Table head={["Name", "Email", "Role", "MFA", "Status", "Last login", ""]}>
          {data!.map((u) => {
            const locked = u.locked_until && new Date(u.locked_until) > new Date();
            return (
              <tr key={u.doctor_id}>
                <td className="px-4 py-2.5 font-medium">{u.name}{u.doctor_id === me && <span className="ml-2 text-xs text-brand-300">(you)</span>}</td>
                <td className="px-4 py-2.5 text-mist-400">{u.email}</td>
                <td className="px-4 py-2.5">
                  <Select
                    className="w-36 py-1.5 text-xs"
                    value={u.role}
                    disabled={u.doctor_id === me || save.isPending}
                    onChange={(e) => save.mutate({ id: u.doctor_id, body: { role: e.target.value } })}
                    aria-label={`Role for ${u.name}`}
                  >
                    {(Object.keys(ROLE_LABEL) as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                  </Select>
                </td>
                <td className="px-4 py-2.5">{u.mfa_enabled ? <Badge tone="ok">on</Badge> : <Badge>off</Badge>}</td>
                <td className="px-4 py-2.5">
                  {u.active === false ? <Badge tone="critical">disabled</Badge> : locked ? <Badge tone="review">locked</Badge> : <Badge tone="ok">active</Badge>}
                </td>
                <td className="px-4 py-2.5 text-xs text-mist-400">{fmtDateTime(u.last_login)}</td>
                <td className="px-4 py-2.5 text-right">
                  {u.doctor_id !== me && (
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" icon={<Lock className="h-3.5 w-3.5" />} onClick={() => lock.mutate({ id: u.doctor_id, minutes: 60 })}>Lock 1h</Button>
                      <Button size="sm" variant="ghost" onClick={() => save.mutate({ id: u.doctor_id, body: { active: u.active === false } })}>
                        {u.active === false ? "Enable" : "Disable"}
                      </Button>
                    </div>
                  )}
                </td>
              </tr>
            );
          })}
        </Table>
      )}
      <NewUserModal open={creating} onClose={() => setCreating(false)} />
    </Card>
  );
}

function KeysPanel() {
  const { data, isLoading, error } = useAdminConfig();
  if (error) return <ErrorState error={error} />;
  if (isLoading || !data) return <LoadingRows />;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardTitle icon={<KeyRound className="h-4 w-4" />}>Encryption keys</CardTitle>
        <p className="text-sm">{data.encryption.algorithm}, fresh 96-bit nonce per message</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {data.encryption.key_ids.map((k) => (
            <Badge key={k} tone={k === data.encryption.active_key_id ? "brand" : "neutral"}>{k}{k === data.encryption.active_key_id ? " · active" : " · decrypt only"}</Badge>
          ))}
        </div>
        <p className="mt-4 text-xs text-mist-500">Rotate by adding a new key to FIELD_ENCRYPTION_KEYS in .env, then run scripts/rotate_keys.py (see docs/KEY_ROTATION.md).</p>
      </Card>
      <Card>
        <CardTitle icon={<KeyRound className="h-4 w-4" />}>Model and report signing</CardTitle>
        <p className="text-sm">{data.signing.algorithm}</p>
        <p className="mt-2 text-xs text-mist-400">Public key fingerprint <span className="hash">{data.signing.public_key_fingerprint ?? "–"}</span></p>
        <p className="mt-2 text-sm">{data.signing.private_key_available ? <Badge tone="ok">private key available</Badge> : <Badge tone="review">private key not configured</Badge>}</p>
        <p className="mt-4 text-xs text-mist-500">Sign new weights with python scripts/sign_model.py. Unsigned weights are refused at load time.</p>
      </Card>
    </div>
  );
}

function ThresholdsPanel() {
  const { data, isLoading } = useAdminConfig();
  if (isLoading || !data) return <LoadingRows />;
  return (
    <Card>
      <CardTitle icon={<SlidersHorizontal className="h-4 w-4" />}>Clinical and ML thresholds</CardTitle>
      <p className="mb-4 text-sm text-mist-400">Read from <span className="font-mono text-brand-300">{data.thresholds_file}</span>. Edit the file and restart the backend to change them. These are engineering defaults, not clinically validated cut-offs.</p>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Object.entries(data.thresholds).map(([group, values]) => (
          <div key={group} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
            <p className="label mb-2 text-brand-300">{group}</p>
            <dl className="space-y-1 text-xs">
              {Object.entries(values).filter(([k]) => !k.startsWith("_")).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3">
                  <dt className="text-mist-400">{k.replace(/_/g, " ")}</dt>
                  <dd className="font-mono text-mist-100">{Array.isArray(v) ? v.join(" – ") : String(v)}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
    </Card>
  );
}

export default function AdminPage() {
  const [tab, setTab] = useState<"users" | "keys" | "thresholds">("users");
  return (
    <div>
      <PageHeader
        eyebrow="Administration"
        title="People, keys and settings"
        subtitle="Admins manage accounts and system settings but make no clinical decisions."
        actions={<Tabs value={tab} onChange={setTab} items={[{ value: "users", label: "Users & roles" }, { value: "keys", label: "Keys & signing" }, { value: "thresholds", label: "Thresholds" }]} />}
      />
      {tab === "users" && <UsersPanel />}
      {tab === "keys" && <KeysPanel />}
      {tab === "thresholds" && <ThresholdsPanel />}
    </div>
  );
}
