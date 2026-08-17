# Cursor Chat: ai-agent-book

## Metadata
- **Project**: ai-agent-book
- **Path**: `/Users/boj`
- **Date**: 2025-10-09 14:00:48
- **Session ID**: `83e063ff-25ad-4e7d-a20b-de54093b8e89`

## Conversation

### 👤 You

Update the design docs: 

remove the parallel processing.

merge queued processing and batching.

there should only be two modes, which should be dynamically determined based on the urgency of the new event:
1. cancellation-based processing: stop the current LLM thinking or synchronous tool call, and immediately append all queued events and the new event to the trajectory, and process the trajectory with LLM.
2. queued processing: queue the event at the end of pending queue. when any tool call of the agent completes, check the pending queue before invoking the LLM. move all events in the pending queue immediately to the end of trajectory, and then use LLM to process it.

In addition, use "trajectory" consistently to refer to all events in a session, rather than conversation history, etc. Use "rollout" consistently to refer to a task or session with one trajectory. This aligns the academic definitions of an agent

---

### 👤 You

Update the design docs: 

remove the parallel processing.

merge queued processing and batching.

there should only be two modes, which should be dynamically determined based on the urgency of the new event:
1. cancellation-based processing: stop the current LLM thinking or synchronous tool call, and immediately append all queued events and the new event to the trajectory, and process the trajectory with LLM.
2. queued processing: queue the event at the end of pending queue. when any tool call of the agent completes, check the pending queue before invoking the LLM. move all events in the pending queue immediately to the end of trajectory, and then use LLM to process it.

In addition, use "trajectory" consistently to refer to all events in a session, rather than conversation history, etc. Use "rollout" consistently to refer to a task or session with one trajectory. This aligns the academic definitions of an agent

---

### 🤖 Cursor Assistant

I'll help you update the design document. Let me first read the current document to understand its structure.

---

### 🤖 Cursor Assistant

Now I'll update the design document according to your requirements. I'll:
1. Remove parallel processing
2. Merge queued processing and batching
3. Keep only two dynamic modes based on urgency
4. Use "trajectory" consistently instead of "conversation history" or "session context"
5. Use "rollout" consistently to refer to a task/session with one trajectory

---

### 🤖 Cursor Assistant

Now let me check if there are any remaining references to update by reading the entire file:

---

### 🤖 Cursor Assistant

Perfect! I've successfully updated the design document with all the requested changes:

## Summary of Changes:

### 1. **Removed Parallel Processing**
   - Eliminated the parallel processing mechanism from section 5.1

### 2. **Merged Queued Processing and Batching**
   - Combined these into a single "Queued Processing" mode that efficiently batches events

### 3. **Two Dynamic Processing Modes**
   - **Cancellation-Based Processing**: For urgent events (user interrupts, supervisor instructions, agent interrupts, urgent external triggers)
     - Stops current LLM thinking or synchronous tool call
     - Appends all queued events + new urgent event to trajectory
     - Processes with LLM immediately
   
   - **Queued Processing**: For non-urgent events (user inputs, agent messages, tool results, timer triggers)
     - Queues events without interrupting ongoing processing
     - When any tool call completes, checks pending queue
     - Moves all pending events to trajectory end, then processes with LLM

### 4. **Consistent Terminology**
   - **"Trajectory"** now consistently refers to all events in a session (replaced "session context", "event history", "conversation history")
   - **"Rollout"** now consistently refers to a task/session with one trajectory (replaced "task" when referring to running instances)
   - **"Rollout Manager"** (replaced "Task Manager")
   - **"Rollout Business State"** (replaced "Task Business State")

The document now aligns with academic definitions where trajectory represents the complete sequence of events in a rollout, matching standard reinforcement learning and agent terminology.

---


*Exported from [Cursor View](https://github.com/saharmor/cursor-view)*