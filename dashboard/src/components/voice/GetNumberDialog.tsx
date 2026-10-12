"use client";

import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { Button, Dialog, Input, Segmented, Select, Skeleton, cn, useToast } from "@/components/ui";
import { TopUpDialog, useBalance } from "@/components/Balance";
import { apiJson } from "@/lib/api";
import { apiSave, useApi } from "@/lib/useApi";
import { formatINR } from "@/lib/voice/api";
import type { AvailableNumber, NumberCountry, PhoneNumber, VoiceAgentSummary } from "@/lib/voice/types";

const CITIES = ["Chennai", "Coimbatore", "Bengaluru", "Hyderabad", "Mumbai", "Pune", "Delhi"];

export const NUMBER_KIND: Record<PhoneNumber["kind"], string> = {
    landline: "Landline", mobile: "Mobile", local: "Local", toll_free: "Toll-free",
};

export const countryName = (code: string) => {
    try { return new Intl.DisplayNames(["en"], { type: "region" }).of(code) ?? code; } catch { return code; }
};

type Address = { customer_name: string; street: string; city: string; region: string; postal_code: string };
const EMPTY_ADDRESS: Address = { customer_name: "", street: "", city: "", region: "", postal_code: "" };

/**
 * India: a guided request (telecom KYC, set up by our team).
 * Other countries: live search of available numbers, bought instantly from the Nimmi balance.
 */
export function GetNumberDialog({ open, onClose, onCreated, agents }: {
    open: boolean; onClose: () => void; onCreated: (n: PhoneNumber) => void; agents: VoiceAgentSummary[];
}) {
    const [where, setWhere] = useState<"india" | "abroad">("india");
    const close = () => { setWhere("india"); onClose(); };

    return (
        <Dialog
            open={open}
            onClose={close}
            title="Get a phone number"
            description="Customers call this number to reach your assistant."
            footer={null}
        >
            <Segmented
                label="Where are your callers?"
                value={where}
                onChange={setWhere}
                options={[{ value: "india", label: "India" }, { value: "abroad", label: "Other countries" }]}
            />
            <div className="mt-5">
                {where === "india"
                    ? <IndiaRequest onCancel={close} onCreated={(n) => { close(); onCreated(n); }} />
                    : <BuyAbroad agents={agents} onCancel={close} onCreated={(n) => { close(); onCreated(n); }} />}
            </div>
        </Dialog>
    );
}

function Footer({ children }: { children: React.ReactNode }) {
    return <div className="flex justify-end gap-2 -mx-5 -mb-4 mt-5 px-5 py-3 border-t border-line bg-stone-50/60 rounded-b-lg">{children}</div>;
}

function IndiaRequest({ onCancel, onCreated }: { onCancel: () => void; onCreated: (n: PhoneNumber) => void }) {
    const toast = useToast();
    const [city, setCity] = useState(CITIES[0]);
    const [busy, setBusy] = useState(false);

    const submit = async () => {
        setBusy(true);
        const res = await apiSave("/api/voice/numbers", "POST", { city });
        setBusy(false);
        if (!res.ok) return toast(res.message);
        onCreated(res.data as PhoneNumber);
    };

    return (
        <>
            <label htmlFor="city" className="text-sm font-medium">City</label>
            <Select id="city" className="mt-1.5" value={city} onChange={(e) => setCity(e.target.value)}>
                {CITIES.map((c) => <option key={c}>{c}</option>)}
            </Select>

            <div className="mt-5 space-y-3 text-[13px] text-stone-600 leading-relaxed">
                <p>
                    <span className="font-medium text-ink">You&apos;ll need two documents.</span>{" "}
                    Telecom rules require them before an Indian number can be issued: your Certificate of Incorporation and GST certificate.
                    Our team sets the number up, usually in 2 to 5 working days.
                </p>
                <p>
                    <span className="font-medium text-ink">For service calls only.</span>{" "}
                    Use it to answer enquiries and call back people who asked. Promotional calls aren&apos;t allowed on these numbers.
                </p>
            </div>

            <Footer>
                <Button variant="ghost" onClick={onCancel}>Cancel</Button>
                <Button variant="primary" onClick={submit} disabled={busy}>{busy ? "Requesting…" : "Request number"}</Button>
            </Footer>
        </>
    );
}

function BuyAbroad({ agents, onCancel, onCreated }: { agents: VoiceAgentSummary[]; onCancel: () => void; onCreated: (n: PhoneNumber) => void }) {
    const toast = useToast();
    const catalog = useApi<{ countries: NumberCountry[]; available: boolean }>("/api/voice/numbers/countries");
    const wallet = useBalance();
    const [country, setCountry] = useState("US");
    const [type, setType] = useState<NumberCountry["types"][number]>("local");
    const [digits, setDigits] = useState("");
    const [results, setResults] = useState<{ monthly_fee: number; numbers: AvailableNumber[] } | null>(null);
    const [searching, setSearching] = useState(false);
    const [searchError, setSearchError] = useState("");
    const [picked, setPicked] = useState<AvailableNumber | null>(null);
    const [botId, setBotId] = useState(agents[0]?.bot_id ?? "");
    const [address, setAddress] = useState<Address>(EMPTY_ADDRESS);
    const [buying, setBuying] = useState(false);
    const [topUp, setTopUp] = useState(false);

    const spec = catalog.data?.countries.find((c) => c.code === country);
    const byArea = country === "US" || country === "CA";

    const search = async (area = digits) => {
        setSearching(true);
        setSearchError("");
        setPicked(null);
        const q = new URLSearchParams({ country, type, [byArea ? "area_code" : "contains"]: area.replace(/\D/g, "") });
        try {
            setResults(await apiJson(`/api/voice/numbers/available?${q}`));
        } catch (e) {
            setResults(null);
            setSearchError((e as Error).message);
        } finally {
            setSearching(false);
        }
    };

    // Search again whenever the country or number type changes.
    useEffect(() => {
        if (catalog.data?.available) search("");
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [country, type, catalog.data?.available]);

    if (catalog.loading) return <Skeleton className="h-40" />;
    if (!catalog.data?.available) {
        return (
            <>
                <p className="text-[13px] text-stone-600 leading-relaxed">Numbers outside India aren&apos;t available on this account yet. Choose India to request a local number.</p>
                <Footer><Button onClick={onCancel}>Close</Button></Footer>
            </>
        );
    }

    const fee = results?.monthly_fee ?? 0;
    const balance = wallet.data?.balance ?? 0;
    const short = fee > balance;
    const addressMissing = !!picked?.address_required &&
        (!address.customer_name.trim() || !address.street.trim() || !address.city.trim() || !address.postal_code.trim());

    const buy = async () => {
        if (!picked) return;
        setBuying(true);
        const res = await apiSave("/api/voice/numbers/buy", "POST", {
            phone_number: picked.phone_number, country, type, bot_id: botId || null,
            address: picked.address_required ? address : null,
        });
        setBuying(false);
        if (!res.ok) return toast(res.message);
        toast(`${picked.display} is yours. It's ready for calls.`);
        onCreated(res.data as PhoneNumber);
    };

    const setAddr = (k: keyof Address, v: string) => setAddress({ ...address, [k]: v });

    return (
        <>
            <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 items-end">
                <div>
                    <label htmlFor="country" className="text-sm font-medium">Country</label>
                    <Select id="country" className="mt-1.5" value={country} onChange={(e) => {
                        const next = catalog.data!.countries.find((c) => c.code === e.target.value)!;
                        setCountry(next.code);
                        if (!next.types.includes(type)) setType(next.types[0]);
                        setDigits("");
                    }}>
                        {catalog.data.countries.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
                    </Select>
                </div>
                <Segmented
                    label="Number type"
                    value={type}
                    onChange={setType}
                    options={(spec?.types ?? ["local"]).map((t) => ({ value: t, label: NUMBER_KIND[t] }))}
                />
            </div>

            <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); search(); }}>
                <Input
                    aria-label={byArea ? "Area code" : "Digits the number contains"}
                    placeholder={byArea ? "Area code, e.g. 415" : "Contains digits, e.g. 20"}
                    inputMode="numeric"
                    value={digits}
                    onChange={(e) => setDigits(e.target.value)}
                />
                <Button type="submit" disabled={searching}><Search size={14} /> Search</Button>
            </form>

            <div className="mt-4">
                {searching ? (
                    <div className="space-y-2"><Skeleton className="h-11" /><Skeleton className="h-11" /><Skeleton className="h-11" /></div>
                ) : searchError ? (
                    <p className="text-[13px] text-signal">{searchError}</p>
                ) : results && !results.numbers.length ? (
                    <p className="text-[13px] text-stone-500">No numbers match. Try another area code, or leave it empty.</p>
                ) : results && (
                    <>
                        <p className="text-[13px] text-stone-500 mb-2">{formatINR(fee)} a month each, charged from your Nimmi balance.</p>
                        <ul role="radiogroup" aria-label="Available numbers" className="max-h-56 overflow-y-auto rounded-md border border-line divide-y divide-line">
                            {results.numbers.map((n) => {
                                const on = picked?.phone_number === n.phone_number;
                                return (
                                    <li key={n.phone_number}>
                                        <button
                                            type="button"
                                            role="radio"
                                            aria-checked={on}
                                            onClick={() => setPicked(n)}
                                            className={cn(
                                                "w-full flex items-center justify-between gap-3 px-3 py-2.5 text-left transition-colors focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-plum",
                                                on ? "bg-plum-tint" : "hover:bg-stone-50",
                                            )}
                                        >
                                            <span className={cn("text-sm tabular-nums", on && "font-medium text-plum")}>{n.display}</span>
                                            <span className="text-xs text-stone-500 truncate">{[n.locality, n.region].filter(Boolean).join(", ")}</span>
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    </>
                )}
            </div>

            {picked && (
                <div className="mt-5 space-y-4">
                    <div>
                        <label htmlFor="answered_by" className="text-sm font-medium">Answered by</label>
                        <Select id="answered_by" className="mt-1.5" value={botId} onChange={(e) => setBotId(e.target.value)}>
                            <option value="">Choose later</option>
                            {agents.map((a) => <option key={a.bot_id} value={a.bot_id}>{a.bot_name}</option>)}
                        </Select>
                    </div>

                    {picked.address_required && (
                        <fieldset>
                            <legend className="text-sm font-medium">Business address</legend>
                            <p className="text-[13px] text-stone-500 mt-0.5">{countryName(country)} requires an address on file for this number.</p>
                            <div className="mt-2 grid grid-cols-2 gap-2">
                                <Input className="col-span-2" aria-label="Business or your name" placeholder="Business or your name" value={address.customer_name} onChange={(e) => setAddr("customer_name", e.target.value)} />
                                <Input className="col-span-2" aria-label="Street address" placeholder="Street address" value={address.street} onChange={(e) => setAddr("street", e.target.value)} />
                                <Input aria-label="City" placeholder="City" value={address.city} onChange={(e) => setAddr("city", e.target.value)} />
                                <Input aria-label="State or region" placeholder="State or region" value={address.region} onChange={(e) => setAddr("region", e.target.value)} />
                                <Input aria-label="Postal code" placeholder="Postal code" value={address.postal_code} onChange={(e) => setAddr("postal_code", e.target.value)} />
                            </div>
                        </fieldset>
                    )}

                    <div className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-md bg-stone-50 border border-line text-[13px]">
                        <span className={short ? "text-signal" : "text-stone-600"}>
                            Balance {formatINR(balance)}
                            {short && `. You need ${formatINR(fee - balance)} more.`}
                        </span>
                        <Button size="sm" variant={short ? "primary" : "ghost"} onClick={() => setTopUp(true)}>Add money</Button>
                    </div>
                </div>
            )}

            <Footer>
                <Button variant="ghost" onClick={onCancel}>Cancel</Button>
                <Button variant="primary" onClick={buy} disabled={!picked || short || addressMissing || buying}>
                    {buying ? "Buying…" : picked ? `Buy for ${formatINR(fee)}/month` : "Choose a number"}
                </Button>
            </Footer>

            <TopUpDialog
                open={topUp}
                onClose={() => setTopUp(false)}
                amounts={wallet.data?.topups ?? [500, 1000, 2000, 5000]}
                needed={Math.max(0, fee - balance)}
                onPaid={wallet.reload}
            />
        </>
    );
}
