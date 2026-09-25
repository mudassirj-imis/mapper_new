import { useMutation, useQuery } from "@tanstack/react-query";

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
