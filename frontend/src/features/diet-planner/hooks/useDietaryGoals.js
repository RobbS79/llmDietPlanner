/**
 * React Query hooks for dietary goals
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createDietaryGoal,
  getDietaryGoalsList,
  getDietaryGoalDetail,
} from '../utils/api';

/**
 * Hook for creating a new dietary goal
 * @returns {Object} mutation object
 */
export function useCreateDietaryGoal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createDietaryGoal,
    onSuccess: () => {
      // Invalidate and refetch goals list
      queryClient.invalidateQueries({ queryKey: ['dietaryGoals'] });
    },
  });
}

/**
 * Hook for fetching list of dietary goals
 * @returns {Object} query object
 */
export function useDietaryGoalsList() {
  return useQuery({
    queryKey: ['dietaryGoals', 'list'],
    queryFn: getDietaryGoalsList,
  });
}

/**
 * Hook for fetching a single dietary goal detail
 * @param {number} goalId
 * @returns {Object} query object
 */
export function useDietaryGoalDetail(goalId) {
  return useQuery({
    queryKey: ['dietaryGoals', goalId],
    queryFn: () => getDietaryGoalDetail(goalId),
    enabled: !!goalId,
  });
}



