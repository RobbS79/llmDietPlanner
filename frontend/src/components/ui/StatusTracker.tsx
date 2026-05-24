const steps = [
  { label: 'Starting', keys: ['pending', 'awaiting_payment'] },
  { label: 'Creating Meals', keys: ['payment_confirmed', 'processing', 'processing_meal_plan'] },
  { label: 'Finding Prices', keys: ['processing_shopping_list'] },
  { label: 'Verifying', keys: ['validating'] },
  { label: 'Complete', keys: ['completed'] },
];

export const StatusTracker = ({ statusData }: { statusData: any }) => {
  const currentStatus = statusData?.goal_status || 'pending';
  const activeIdx = steps.findIndex(s => s.keys.includes(currentStatus));

  return (
    <div className="space-y-6 text-left border-l-2 border-zinc-800 pl-6 mt-12 max-w-xs mx-auto md:mx-0">
      {steps.map((step, idx) => {
        const isPast = idx < activeIdx;
        const isCurrent = idx === activeIdx;
        return (
          <div key={idx} className={`relative flex items-center gap-4 transition-all duration-500 ${idx <= activeIdx ? 'opacity-100' : 'opacity-20'}`}>
            <div className={`w-2.5 h-2.5 rounded-full z-10 ${isPast ? 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]' : isCurrent ? 'bg-indigo-500 animate-pulse' : 'bg-zinc-800'}`} />
            <span className={`text-[10px] font-black uppercase tracking-widest ${isCurrent ? 'text-indigo-400' : isPast ? 'text-emerald-400' : 'text-zinc-600'}`}>
              {step.label}
            </span>
          </div>
        );
      })}
    </div>
  );
};
