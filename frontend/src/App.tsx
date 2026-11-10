import { Route, Router, Switch } from "wouter";
import { useHashLocation } from "wouter/use-hash-location";

import { Dashboard } from "./pages/Dashboard";

function ChartRoute({ params }: { params: { symbol: string } }) {
  return <Dashboard chartSymbol={decodeURIComponent(params.symbol)} />;
}

export default function App() {
  return (
    <Router hook={useHashLocation}>
      <Switch>
        <Route path="/chart/:symbol" component={ChartRoute} />
        <Route>
          <Dashboard />
        </Route>
      </Switch>
    </Router>
  );
}
