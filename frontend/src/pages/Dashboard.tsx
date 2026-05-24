import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Plus, MapPin, ChevronRight, Box, ArrowRight } from 'lucide-react';
import { api } from '@/lib/api';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { LoadingScreen } from '@/components/ui/LoadingScreen';

export const Dashboard = () => {
  const navigate = useNavigate();
  const { data: goals, isLoading } = useQuery({
    queryKey: ['goals'],
    queryFn: () => api.get('/goals/list/').then(res => res.data.data),
  });

  if (isLoading) return <LoadingScreen message="Loading your meal plans..." />;

  return (
    <MainLayout>
      <div className="max-w-7xl mx-auto px-6 py-12 w-full">
        <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-8 mb-16 text-left">
          <div className="space-y-3">
            <h1 className="text-5xl font-black text-white tracking-tighter uppercase italic leading-none">
              Your<br /><span className="text-indigo-500 not-italic text-6xl">Plans.</span>
            </h1>
          </div>
          <button
            onClick={() => navigate('/create')}
            className="h-14 px-10 bg-white text-black font-black uppercase text-[10px] tracking-[0.2em] rounded-xl hover:bg-zinc-200 transition-all shadow-2xl active:scale-95 flex items-center gap-3 shrink-0"
          >
            <Plus size={20} strokeWidth={4} /> New Plan
          </button>
        </header>

        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {goals?.length === 0 ? (
            <div className="col-span-full py-40 flex flex-col items-center justify-center border border-zinc-800 rounded-[2.5rem] bg-zinc-900/10 text-center">
              <Box size={64} className="text-zinc-800 mb-8" />
              <p className="text-zinc-600 font-bold uppercase tracking-widest text-xs mb-10 italic">No meal plans yet</p>
              <button onClick={() => navigate('/create')} className="text-indigo-500 font-black uppercase text-[10px] tracking-widest hover:underline flex items-center gap-2">
                Create your first plan <ArrowRight size={14} />
              </button>
            </div>
          ) : (
            goals?.map((goal: any) => (
              <Card
                key={goal.id}
                className="p-8 hover:bg-zinc-900 hover:border-indigo-500/30 cursor-pointer group flex flex-col h-full text-left"
                onClick={() => navigate(`/plan/${goal.id}`)}
              >
                <div className="flex justify-between items-start mb-12">
                  <Badge variant={goal.status === 'completed' ? 'emerald' : goal.status === 'failed' ? 'rose' : 'blue'}>
                    {goal.status.replace(/_/g, ' ')}
                  </Badge>
                  <span className="text-[10px] font-black text-zinc-700 uppercase tracking-widest">
                    #{goal.id}
                  </span>
                </div>

                <h3 className="text-2xl font-black text-white mb-8 leading-tight uppercase tracking-tight italic group-hover:text-indigo-400 transition-colors line-clamp-3">
                  {goal.prompt}
                </h3>

                <div className="mt-auto pt-8 flex flex-col gap-4 border-t border-zinc-800">
                  <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-zinc-500 italic">
                    <span className="flex items-center gap-2"><MapPin size={12} className="text-indigo-500" /> {goal.city}</span>
                    <span className="bg-zinc-800 px-2 py-0.5 rounded text-zinc-400">{goal.num_days} days</span>
                  </div>
                  <div className="flex justify-between items-center text-[9px] font-black text-zinc-800 uppercase tracking-[0.4em] pt-1">
                    <span>{new Date(goal.created_at).toLocaleDateString()}</span>
                    <ChevronRight size={16} className="group-hover:translate-x-1 transition-transform group-hover:text-indigo-500" />
                  </div>
                </div>
              </Card>
            ))
          )}
        </div>
      </div>
    </MainLayout>
  );
};
