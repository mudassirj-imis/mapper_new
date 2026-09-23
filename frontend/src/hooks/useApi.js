import { useMutation, useQuery } from '@tanstack/react-query';

/**
 * Thin wrappers around React Query so every module uses one consistent
 * data-fetching surface.
 *
 *   const { data, isLoading, error } = useApiQuery(['endpoints'], endpointService.getEndpoints);
 *   const save = useApiMutation(endpointService.saveCompleteMapping, {
 *     onSuccess: () => showSnackbar('Saved', 'success'),
 *   });
 */

export function useApiQuery(key, queryFn, options = {}) {
  return useQuery({
    queryKey: Array.isArray(key) ? key : [key],
    queryFn,
    ...options,
  });
}

export function useApiMutation(mutationFn, options = {}) {
  return useMutation({
    mutationFn,
    ...options,
  });
}

export default { useApiQuery, useApiMutation };
