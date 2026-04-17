import { useParams } from "react-router-dom";
export default function MarketTicker() {
  const { ticker } = useParams<{ ticker: string }>();
  return <main className="p-6"><h1 className="text-2xl font-semibold">{ticker?.toUpperCase()}</h1></main>;
}
