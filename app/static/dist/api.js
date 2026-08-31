export class ApiError extends Error {
    status;
    constructor(message, status) {
        super(message);
        this.status = status;
        this.name = "ApiError";
    }
}
async function request(path, options) {
    const response = await fetch(path, {
        cache: "no-store",
        ...options,
        headers: {
            Accept: "application/json",
            ...options?.headers,
        },
    });
    if (!response.ok) {
        throw new ApiError(`Request failed with status ${response.status}`, response.status);
    }
    return response.json();
}
export function getJson(path) {
    return request(path);
}
export function postJson(path, body) {
    return request(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
}
