from local_functions.main import global_vars as gl


def exe_orders(orders):
    '''
    # Core Function: Executing Orders
    ## 1) Takes suggested orders and puts them through a simluation 
       to see whether or not they would be filled.

    ## 2) If there are new fills, update the 'filled_orders' and 'current_positions' vars.  
    '''
    if gl.loop_feedback == False:
        return

    # Queue Orders
    orders = queue_order_center(orders)

    cancel_ids = check_cancel()

    # EXECUTIONS
    new_fills, new_cancels = execute_direct(orders, cancel_ids)

    gl.log_funcs.log_filled_and_open(new_fills)

    if len(new_fills) != 0:
        reset_buy_clock(new_fills)
        update_filled_orders(new_fills)
        update_current_positions(new_fills)

    if len(new_cancels) != 0:
        cancelled_orders = gl.cancelled_orders

        cancelled_orders = cancelled_orders[~cancelled_orders.order_id.isin(
            new_cancels.order_id)]

        cancelled_orders = cancelled_orders.append(
            new_cancels, sort=False)

        gl.cancelled_orders = cancelled_orders


def execute_direct(orders, cancel_ids):
    '''
    # Redirect for executing orders.  
    '''
    if gl.trade_mode == 'csv':
        return gl.sim_exe.sim_execute_orders(orders, cancel_ids)
    else:
        return live_executions(orders)


def live_executions(new_orders):
    '''    
    Live Equivalent to sim_executions
    '''
    def live_get_open_orders():
        pass

    def live_cancellation():
        pass

    def live_send_orders(new_orders):
        pass

    live_send_orders(new_orders)
    live_get_open_orders()
    live_cancellation()


def update_filled_orders(new_fills):
    '''
    # Update Filled Orders
    Simple function to append new fills to existing 'filled_orders' global variable. 

    '''
    filled_orders = gl.filled_orders
    filled_orders = filled_orders.append(new_fills, sort=False)
    gl.filled_orders = filled_orders


def update_current_positions(new_fills):
    '''
    # Update Current Positions
    Takes current positions and adds new fills. Function then calculates which positions are still active. 
    e.g.: if you have two positions open, then sell one half, this will sort out the remaining position. 
    '''

    df = new_fills
    df = gl.current_positions.append(df, sort=False)
    df = df.reset_index(drop=True)

    buys = df[df['buy_or_sell'] == 'BUY']
    sells = df[df['buy_or_sell'] == 'SELL']
    realized = 0

    if len(sells) != 0:
        for qty, price in zip(sells.qty, sells.exe_price):
            remainder = qty
            while remainder > 0:

                first_row = buys.index.tolist()[0]
                # if there are more shares sold than the one row
                # calculate the remainder and drop the first row...
                if (buys.at[first_row, 'qty'] - remainder) <= 0:
                    realized += (price - buys.at[first_row,
                                                 'exe_price']) * buys.at[first_row, 'qty']
                    diff = int(remainder - buys.at[first_row, 'qty'])
                    buys = buys.drop(first_row)
                    # I use this workaround because the loop is based on this value
                    # If the value happens to be zero, the loop will break.
                    remainder = diff
                # if the shares sold are not greater than the row's qty
                # calculate the new row's value, stop the loop...
                elif (buys.at[first_row, 'qty'] - remainder) > 0:
                    realized += (price -
                                 buys.at[first_row, 'exe_price']) * remainder
                    buys.at[first_row, 'qty'] = buys.at[first_row,
                                                        'qty'] - remainder
                    remainder = 0

    current_positions = buys
    current_positions['cash'] = current_positions.qty*current_positions.exe_price
    gl.current_positions = current_positions
    # if realized != 0:
    if len(current_positions) == 0:
        unrealized = 0
    else:
        unrealized = 'skip'
    gl.common.update_pl(realized, unrealized)
    gl.common.update_ex()
    gl.common.current_average(new_avg=True)


def reset_buy_clock(new_fills):
    if len(new_fills[new_fills['buy_or_sell'] == 'BUY']) != 0:
        gl.buy_clock = gl.configure.misc['buy_clock_countdown_amount']


def queue_order_center(orders):
    q_orders = gl.queued_orders
    ready = gl.pd.DataFrame()
    already_dropped_ids = []

    if len(q_orders) != 0:
        q_orders = q_orders.reset_index(drop=True)
        drop_indexes = []
        for row in q_orders.index:
            qs = q_orders.at[row, 'queue_spec']

            if qs[0:4] == 'time':
                qs = int(qs.split(':')[1]) - 1
                q_orders.at[row, 'queue_spec'] = qs
                if qs == 0:
                    ready = ready.append(q_orders.iloc[row], sort=False)
                    drop_indexes.append(row)

            elif qs[0:4] == 'fill':
                # 'x' here is a character passed on the last partition of any order.
                # Because of partial fills, multiple filled orders may have the same name.
                order_id = qs[5:]+'x'
                order_id_no_x = int(qs[5:])
                if len(gl.filled_orders) != 0:
                    # If filled 
                    if order_id in gl.filled_orders.order_id.tolist():
                        ready = ready.append(q_orders.iloc[row], sort=False)
                        drop_indexes.append(row)
                    # If cancelled 
                    elif order_id_no_x in gl.cancelled_orders.order_id.to_list():
                        drop_indexes.append(row)
                        already_dropped_ids.append(q_orders.at[row, 'order_id'])
                    # If domino order from previous queued. 
                    elif order_id_no_x in already_dropped_ids:
                        drop_indexes.append(row)
                        already_dropped_ids.append(q_orders.at[row, 'order_id'])
                        

        q_orders = q_orders.drop(drop_indexes)

    for_q = gl.pd.DataFrame()
    if len(orders) != 0:
        for_q = orders[orders['queue_spec'] != 'nan']
        if len(for_q) != 0:
            q_orders = q_orders.append(for_q, sort=False)

    gl.queued_orders = q_orders

    if len(orders) != 0:
        immediately_ready = orders[orders['queue_spec'] == 'nan']
        ready = ready.append(immediately_ready, sort=False)

    ready = gl.order_tools.format_orders(ready)
    return ready


def check_cancel():
    cancelled_orders = gl.cancelled_orders
    open_orders = gl.open_orders
    still_waiting = []
    if len(cancelled_orders) != 0:
        cancelled_orders = cancelled_orders.reset_index(drop=True)
        still_waiting = cancelled_orders[cancelled_orders['status'] ==
                                         'waiting'].order_id.to_list()

    if len(open_orders) == 0:
        return []

    # 1) Reset the index so we can keep track of index values.

    open_orders = open_orders.reset_index(drop=True)

    potential_cancels = open_orders[~open_orders.order_id.isin(still_waiting)]

    for_cancellation = []
    for cancel_spec, order_id, exe_price, duration, index in zip(potential_cancels.cancel_spec,
                                                                 potential_cancels.order_id,
                                                                 potential_cancels.exe_price,
                                                                 potential_cancels.wait_duration,
                                                                 potential_cancels.index):

        if cancel_spec == None:
            continue
        # Example cancel_spec : r'p:%1,t:5'
        xptype = cancel_spec.split(',')[0].split(':')[1][0]
        # x time
        xtime = int(cancel_spec.split(',')[1].split(':')[1])
        # x percent
        xp = (cancel_spec.split(',')[0].split(':')[1].split(xptype)[1])
        p_upper, p_lower = list(map(float, xp.split('/')))
        if xptype == '%':
            p_upper = exe_price + (exe_price*(p_upper*.01))
            p_lower = exe_price - (exe_price*(p_lower*.01))

        if order_id >= 25:
            s = 10
        cancel = False
        # Time Out
        # If the order is filling, give it more time. 
        if len(gl.filled_orders) != 0:
            partial_fill = order_id in gl.filled_orders.order_id.to_list()
            if partial_fill:
                duration = gl.common.sec_since_last_fill(order_id)
        if duration >= xtime:
            cancel = 'time out'
            for_cancellation.append(order_id)

        # Price Drop
        elif gl.current['close'] < p_lower:
            cancel = 'price drop'
            for_cancellation.append(order_id)

        # Price Spike
        elif gl.current['close'] > p_upper:
            cancel = 'price spike'
            for_cancellation.append(order_id)

        if cancel != False:
            gl.log_funcs.log(f'cancellation sent ({cancel}), id: {order_id}')

    new_cancels = open_orders[open_orders.order_id.isin(for_cancellation)]
    new_cancels['status'] = 'waiting'

    gl.cancelled_orders = cancelled_orders.append(new_cancels, sort=False)

    # return list of order ids for cancellation.
    cancel_ids = new_cancels.order_id.tolist()
    return cancel_ids
