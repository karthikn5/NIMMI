/** Structured data for search engines. "<" is escaped so no text in it can close the script tag. */
export default function JsonLd({ data }: { data: object | object[] }) {
    const items = Array.isArray(data) ? data : [data];
    return (
        <>
            {items.map((item, i) => (
                <script key={i} type="application/ld+json"
                        dangerouslySetInnerHTML={{ __html: JSON.stringify(item).replace(/</g, "\\u003c") }} />
            ))}
        </>
    );
}
