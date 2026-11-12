import { SlidePin } from './SlidePin.js';
import { TumorBoardNote } from './TumorBoardNote.js';
import { WardFlowTriageReview } from './WardFlowTriageReview.js';

export type AppSchema = {
  SlidePin: SlidePin;
  TumorBoardNote: TumorBoardNote;
  WardFlowTriageReview: WardFlowTriageReview;
};

export const schema = [SlidePin, TumorBoardNote, WardFlowTriageReview];
