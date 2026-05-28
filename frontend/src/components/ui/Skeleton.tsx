export const Skeleton = ({ className = '' }: { className?: string }) => (
  <div className={`animate-pulse bg-slate-600/50 rounded-xl ${className}`} />
);

export const CardSkeleton = () => (
  <div className="bg-slate-700/50 border border-slate-600 rounded-2xl p-8 space-y-6">
    <div className="flex justify-between">
      <Skeleton className="h-6 w-20 rounded-full" />
      <Skeleton className="h-4 w-12" />
    </div>
    <Skeleton className="h-6 w-3/4" />
    <Skeleton className="h-6 w-1/2" />
    <Skeleton className="h-6 w-2/3" />
    <div className="pt-6 border-t border-slate-600 space-y-3">
      <div className="flex justify-between">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-16" />
      </div>
      <div className="flex justify-between">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-4 w-4" />
      </div>
    </div>
  </div>
);

export const MealCardSkeleton = () => (
  <div className="bg-slate-700/50 border border-slate-600 rounded-2xl p-10 space-y-8">
    <div className="flex justify-between">
      <Skeleton className="h-7 w-24 rounded-lg" />
      <Skeleton className="h-7 w-32 rounded-lg" />
    </div>
    <Skeleton className="h-10 w-3/4" />
    <Skeleton className="h-5 w-full" />
    <div className="grid grid-cols-4 gap-4 pt-6 border-t border-slate-600">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="space-y-2">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="h-6 w-12" />
        </div>
      ))}
    </div>
  </div>
);

export const ShoppingItemSkeleton = () => (
  <div className="border-b border-slate-600 pb-6 space-y-3">
    <div className="flex justify-between">
      <Skeleton className="h-5 w-32" />
      <Skeleton className="h-5 w-16" />
    </div>
    <div className="flex justify-between">
      <Skeleton className="h-4 w-20" />
      <Skeleton className="h-3 w-24" />
    </div>
  </div>
);
