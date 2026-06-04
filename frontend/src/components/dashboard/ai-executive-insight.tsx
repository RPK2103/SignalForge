import { Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { aiExecutiveInsight } from "@/lib/demo-data";

export function AiExecutiveInsight() {
  return (
    <Card className="border border-blue-200/80 bg-blue-50/40 shadow-sm">
      <CardHeader className="border-b border-blue-200/60 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="flex size-8 items-center justify-center rounded-md bg-blue-600 text-white">
              <Sparkles className="size-4" />
            </div>
            <CardTitle className="text-lg">AI Executive Insight</CardTitle>
          </div>
          <Badge
            variant="outline"
            className="border-blue-200 bg-white/80 font-normal text-blue-700"
          >
            Powered by Azure OpenAI
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-3">
        <p className="text-sm leading-relaxed text-foreground/90">
          {aiExecutiveInsight}
        </p>
      </CardContent>
    </Card>
  );
}
