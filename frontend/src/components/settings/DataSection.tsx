import { useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { useToast } from '@/components/ui/Toast';
import { triggerDataExport, extractApiError } from '@/lib/settings';

export function DataSection() {
  const toast = useToast();
  const [loading, setLoading] = useState(false);

  const handleDownload = async () => {
    if (loading) return;
    setLoading(true);
    try {
      await triggerDataExport();
    } catch (err) {
      toast.error(extractApiError(err, 'Export dat se nepodařilo stáhnout.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card variant="paper" className="p-8 space-y-4">
      <h2 className="font-display text-xl font-black text-ink uppercase italic tracking-tight">Moje data</h2>
      <p className="text-xs text-muted font-bold max-w-md">Stáhněte si kopii svých dat ve formátu JSON.</p>
      <button
        type="button"
        onClick={handleDownload}
        disabled={loading}
        className="flex items-center gap-3 px-8 h-12 bg-green hover:bg-green-mid text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-all active:scale-[0.98] disabled:opacity-50"
      >
        {loading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
        {loading ? 'Připravuji…' : 'Stáhnout moje data'}
      </button>
    </Card>
  );
}
