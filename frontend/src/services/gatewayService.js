import api from "./api";

export const mapAndCall = async (data) => {
	const { targetUrl, targetMethod, requestData, headers, endpointId } = data;
	const response = await api.post(
		"/map-and-call",
		{
			targetUrl,
			targetMethod,
			requestData,
			headers,
			endpointId,
		},
		{
			timeout: 90000,
		},
	);
	return response.data;
};

export default { mapAndCall };
