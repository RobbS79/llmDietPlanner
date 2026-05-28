import { useState, useRef, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Upload, FileText, CheckCircle, AlertCircle, Loader2, X, Trash2 } from 'lucide-react';
import { api } from '@/lib/api';

interface Protocol {
  id: number;
  name: string;
  pdf_filename: string;
  pdf_size_bytes: number | null;
  processing_status: string;
  processing_error: string;
  structured_constraints: string | null;
  created_at: string;
}

interface ProtocolUploadProps {
  onProtocolSelect: (protocolId: number | null) => void;
  selectedProtocolId: number | null;
}

export const ProtocolUpload = ({ onProtocolSelect, selectedProtocolId }: ProtocolUploadProps) => {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploadError, setUploadError] = useState('');

  const { data: protocols } = useQuery<Protocol[]>({
    queryKey: ['protocols'],
    queryFn: () => api.get('/protocols/').then(res => res.data.data),
  });

  const processingProtocol = protocols?.find(
    p => p.processing_status === 'pending' || p.processing_status === 'processing'
  );

  useQuery({
    queryKey: ['protocol-status', processingProtocol?.id],
    queryFn: () => api.get(`/protocols/${processingProtocol!.id}/`).then(res => res.data.data),
    enabled: !!processingProtocol,
    refetchInterval: 3000,
    refetchIntervalInBackground: false,
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData();
      formData.append('pdf_file', file);
      formData.append('name', file.name.replace(/\.pdf$/i, ''));
      return api.post('/protocols/upload/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
    },
    onSuccess: () => {
      setUploadError('');
      queryClient.invalidateQueries({ queryKey: ['protocols'] });
    },
    onError: (err: any) => {
      setUploadError(err.response?.data?.error || 'Upload failed');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/protocols/${id}/`),
    onSuccess: (_, deletedId) => {
      if (selectedProtocolId === deletedId) onProtocolSelect(null);
      queryClient.invalidateQueries({ queryKey: ['protocols'] });
    },
  });

  const validateAndUpload = useCallback((file: File) => {
    setUploadError('');
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setUploadError('Pouze PDF soubory jsou povoleny');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setUploadError('Soubor je příliš velký (max 10 MB)');
      return;
    }
    uploadMutation.mutate(file);
  }, [uploadMutation]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    const file = e.dataTransfer.files[0];
    if (file) validateAndUpload(file);
  }, [validateAndUpload]);

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) validateAndUpload(file);
    e.target.value = '';
  };

  const completedProtocols = protocols?.filter(p => p.processing_status === 'completed') || [];

  const statusIcon = (s: string) => {
    switch (s) {
      case 'completed': return <CheckCircle size={14} className="text-emerald-500" />;
      case 'failed': return <AlertCircle size={14} className="text-rose-500" />;
      default: return <Loader2 size={14} className="text-blue-400 animate-spin" />;
    }
  };

  const formatSize = (bytes: number | null) => {
    if (!bytes) return '';
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="space-y-4">
      {/* Previously uploaded protocols */}
      {completedProtocols.length > 0 && (
        <div className="space-y-2">
          <span className="text-[9px] font-black uppercase tracking-widest text-zinc-400">
            Nahrané protokoly
          </span>
          <div className="space-y-1.5">
            {completedProtocols.map(p => (
              <div
                key={p.id}
                className={`flex items-center gap-3 px-4 py-3 rounded-xl border transition-all cursor-pointer group ${
                  selectedProtocolId === p.id
                    ? 'border-emerald-500 bg-emerald-500/5'
                    : 'border-slate-600 bg-slate-900 hover:border-slate-500'
                }`}
                onClick={() => onProtocolSelect(selectedProtocolId === p.id ? null : p.id)}
              >
                <FileText size={16} className={selectedProtocolId === p.id ? 'text-emerald-500' : 'text-zinc-300'} />
                <div className="flex-1 min-w-0">
                  <p className={`text-xs font-bold truncate ${selectedProtocolId === p.id ? 'text-white' : 'text-zinc-200'}`}>
                    {p.name}
                  </p>
                  <p className="text-[9px] text-zinc-400">{formatSize(p.pdf_size_bytes)}</p>
                </div>
                {selectedProtocolId === p.id && (
                  <CheckCircle size={16} className="text-emerald-500 shrink-0" />
                )}
                <button
                  onClick={(e) => { e.stopPropagation(); deleteMutation.mutate(p.id); }}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:bg-slate-600 rounded transition-all shrink-0"
                >
                  <Trash2 size={12} className="text-zinc-300 hover:text-rose-400" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Processing indicator */}
      {processingProtocol && (
        <div className="flex items-center gap-3 px-4 py-3 bg-blue-500/5 border border-blue-500/20 rounded-xl">
          {statusIcon(processingProtocol.processing_status)}
          <span className="text-xs font-bold text-blue-400">
            {processingProtocol.processing_status === 'pending' ? 'Ve frontě...' : 'Zpracovávám PDF...'}
          </span>
          <span className="text-[9px] text-zinc-300 ml-auto">{processingProtocol.pdf_filename}</span>
        </div>
      )}

      {/* Failed protocols */}
      {protocols?.filter(p => p.processing_status === 'failed').map(p => (
        <div key={p.id} className="flex items-center gap-3 px-4 py-3 bg-rose-500/5 border border-rose-500/20 rounded-xl">
          <AlertCircle size={14} className="text-rose-500 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-xs font-bold text-rose-400 truncate">{p.name}</p>
            <p className="text-[9px] text-zinc-300 truncate">{p.processing_error}</p>
          </div>
          <button
            onClick={() => deleteMutation.mutate(p.id)}
            className="p-1 hover:bg-slate-600 rounded transition-all shrink-0"
          >
            <X size={12} className="text-zinc-300" />
          </button>
        </div>
      ))}

      {/* Upload zone */}
      <div
        className={`relative border-2 border-dashed rounded-xl p-6 text-center transition-all cursor-pointer ${
          dragActive
            ? 'border-emerald-500 bg-emerald-500/5'
            : 'border-slate-600 hover:border-zinc-600'
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={handleFileInput}
          className="hidden"
        />
        {uploadMutation.isPending ? (
          <div className="flex items-center justify-center gap-3">
            <Loader2 size={20} className="text-emerald-500 animate-spin" />
            <span className="text-xs font-bold text-zinc-200">Nahrávám...</span>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <Upload size={20} className={dragActive ? 'text-emerald-500' : 'text-zinc-400'} />
            <p className="text-[10px] font-black uppercase tracking-widest text-zinc-300">
              {dragActive ? 'Pusťte soubor' : 'Nahrát PDF protokol'}
            </p>
            <p className="text-[9px] text-zinc-400">PDF, max 10 MB</p>
          </div>
        )}
      </div>

      {uploadError && (
        <div className="flex items-center gap-2 text-rose-400 text-xs font-bold">
          <AlertCircle size={14} />
          <span>{uploadError}</span>
        </div>
      )}
    </div>
  );
};
