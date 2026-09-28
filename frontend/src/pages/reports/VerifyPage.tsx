import { useParams } from "react-router-dom";
import { Logo } from "@/components/layout/Logo";
import { VerifyPanel } from "@/components/VerifyPanel";

/** Public page opened from the QR code on a printed report. No login, no patient data shown. */
export default function VerifyPage() {
  const { reportId } = useParams();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-5 py-12">
      <div className="w-full max-w-xl">
        <div className="mb-8 flex justify-center"><Logo /></div>
        <div className="glass-strong p-6 md:p-8">
          <h1 className="text-2xl font-bold">Verify a PerioVision report</h1>
          <p className="mt-1 text-sm text-mist-400">Checks the report's RSA-PSS digital signature. Nothing about the patient is revealed.</p>
          <div className="mt-6">
            <VerifyPanel initialId={reportId ?? ""} />
          </div>
        </div>
      </div>
    </div>
  );
}
